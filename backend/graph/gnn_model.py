"""
GraphSAGE GNN for stock direction prediction.
Trained on Tier 1+2 historical data. Inference on Tier 2 only.
Node features: [price_change_pct, volume_zscore, sentiment_score, pe_ratio, momentum_14d]
"""

import logging
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F

import database
from config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

logger = logging.getLogger(__name__)

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "gnn_model.pt")
FEATURE_DIM = 5
HIDDEN_DIM = 64
NUM_CLASSES = 3  # 0=down, 1=flat, 2=up


# ---------------------------------------------------------------------------
# Model definition
# ---------------------------------------------------------------------------

class GraphSAGELayer(torch.nn.Module):
    def __init__(self, in_dim: int, out_dim: int):
        super().__init__()
        self.linear = torch.nn.Linear(in_dim * 2, out_dim)

    def forward(self, x: torch.Tensor, adj: torch.Tensor) -> torch.Tensor:
        # adj: (N, N) sparse-ish binary/weighted adjacency
        deg = adj.sum(dim=1, keepdim=True).clamp(min=1)
        agg = (adj @ x) / deg  # mean aggregation
        combined = torch.cat([x, agg], dim=-1)
        return F.relu(self.linear(combined))


class StockGNN(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.conv1 = GraphSAGELayer(FEATURE_DIM, HIDDEN_DIM)
        self.conv2 = GraphSAGELayer(HIDDEN_DIM, HIDDEN_DIM)
        self.classifier = torch.nn.Linear(HIDDEN_DIM, NUM_CLASSES)
        self.dropout = torch.nn.Dropout(0.3)

    def forward(self, x: torch.Tensor, adj: torch.Tensor) -> torch.Tensor:
        h = self.conv1(x, adj)
        h = self.dropout(h)
        h = self.conv2(h, adj)
        return self.classifier(h)


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------

def _get_features_for_tickers(tickers: list[str]) -> tuple[torch.Tensor, list[str]]:
    if not tickers:
        return torch.zeros(0, FEATURE_DIM), []

    conn = database.get_connection()
    try:
        valid_tickers = []
        features = []

        for ticker in tickers:
            try:
                price_rows = conn.execute("""
                    SELECT close, volume FROM price_history
                    WHERE ticker=? AND interval='1d'
                    ORDER BY date DESC LIMIT 30
                """, (ticker,)).fetchall()

                sent_row = conn.execute("""
                    SELECT composite_score FROM sentiment_scores
                    WHERE ticker=? ORDER BY date DESC LIMIT 1
                """, (ticker.split(".")[0],)).fetchone()

                fund_row = conn.execute("""
                    SELECT pe_ratio FROM fundamentals WHERE ticker=?
                """, (ticker,)).fetchone()

                if not price_rows or len(price_rows) < 2:
                    continue

                closes = [r["close"] for r in price_rows if r["close"]]
                volumes = [r["volume"] for r in price_rows if r["volume"]]
                if len(closes) < 2:
                    continue

                pct_change = (closes[0] - closes[1]) / closes[1] if closes[1] != 0 else 0
                avg_vol = np.mean(volumes) if volumes else 1
                vol_zscore = (volumes[0] - avg_vol) / (np.std(volumes) + 1e-9) if volumes else 0
                sentiment = float(sent_row["composite_score"]) if sent_row else 0.0
                pe = float(fund_row["pe_ratio"]) if fund_row and fund_row["pe_ratio"] else 15.0
                pe_norm = min(max((pe - 10) / 40, -1), 1)  # normalize PE to [-1, 1]

                # 14-day momentum
                momentum = (closes[0] - closes[min(14, len(closes) - 1)]) / \
                           (closes[min(14, len(closes) - 1)] + 1e-9) if len(closes) > 1 else 0

                features.append([pct_change, vol_zscore, sentiment, pe_norm, momentum])
                valid_tickers.append(ticker)
            except Exception as exc:
                logger.debug("Feature extraction failed for %s: %s", ticker, exc)

    finally:
        conn.close()

    if not features:
        return torch.zeros(0, FEATURE_DIM), []

    x = torch.tensor(features, dtype=torch.float32)
    return x, valid_tickers


def _build_adjacency(tickers: list[str]) -> torch.Tensor:
    """Build sparse adjacency from Neo4j correlations."""
    n = len(tickers)
    adj = torch.eye(n)  # self-loops
    idx = {t: i for i, t in enumerate(tickers)}

    try:
        from neo4j import GraphDatabase
        drv = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        with drv.session() as sess:
            result = sess.run("""
                MATCH (a:Stock)-[r:CORRELATES_WITH]-(b:Stock)
                WHERE a.ticker IN $tickers AND b.ticker IN $tickers
                RETURN a.ticker AS t1, b.ticker AS t2, r.weight AS w
            """, tickers=tickers)
            for rec in result:
                i, j = idx.get(rec["t1"]), idx.get(rec["t2"])
                if i is not None and j is not None:
                    adj[i, j] = float(rec["w"])
                    adj[j, i] = float(rec["w"])
        drv.close()
    except Exception as exc:
        logger.warning("Could not build adjacency from Neo4j: %s — using identity", exc)

    return adj


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train():
    """Train GNN on Tier 1+2 tickers with historical data. Run weekly."""
    conn = database.get_connection()
    try:
        rows = conn.execute(
            "SELECT ticker FROM ticker_universe WHERE active=1 AND tier>=1"
        ).fetchall()
        tickers = [r["ticker"] for r in rows]
    finally:
        conn.close()

    if len(tickers) < 10:
        logger.warning("Too few tickers for GNN training (%d)", len(tickers))
        return

    logger.info("Building GNN training data for %d tickers", len(tickers))
    x, valid_tickers = _get_features_for_tickers(tickers)
    if x.shape[0] < 5:
        logger.warning("Too few valid feature vectors for training")
        return

    adj = _build_adjacency(valid_tickers)

    # Labels: next-day direction from price history
    labels = []
    conn = database.get_connection()
    try:
        for ticker in valid_tickers:
            rows = conn.execute("""
                SELECT close FROM price_history
                WHERE ticker=? AND interval='1d' ORDER BY date DESC LIMIT 3
            """, (ticker,)).fetchall()
            if len(rows) >= 2:
                chg = (rows[0]["close"] - rows[1]["close"]) / (rows[1]["close"] + 1e-9)
                label = 2 if chg > 0.005 else (0 if chg < -0.005 else 1)
            else:
                label = 1
            labels.append(label)
    finally:
        conn.close()

    y = torch.tensor(labels, dtype=torch.long)
    model = StockGNN()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.01, weight_decay=1e-4)

    model.train()
    for epoch in range(100):
        optimizer.zero_grad()
        out = model(x, adj)
        loss = F.cross_entropy(out, y)
        loss.backward()
        optimizer.step()
        if epoch % 20 == 0:
            logger.debug("GNN epoch %d loss=%.4f", epoch, loss.item())

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    torch.save({"state_dict": model.state_dict(), "tickers": valid_tickers}, MODEL_PATH)
    logger.info("GNN model saved to %s", MODEL_PATH)


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------

def predict(tickers: list[str]) -> dict[str, dict]:
    """Returns {ticker: {score: float, direction: 'up'|'down'|'flat'}}"""
    x, valid_tickers = _get_features_for_tickers(tickers)
    if x.shape[0] == 0:
        return {}

    model = StockGNN()
    if os.path.exists(MODEL_PATH):
        ckpt = torch.load(MODEL_PATH, map_location="cpu")
        model.load_state_dict(ckpt["state_dict"])
    else:
        logger.warning("GNN model not trained yet — using random init")

    adj = _build_adjacency(valid_tickers)
    model.eval()
    with torch.no_grad():
        logits = model(x, adj)
        probs = F.softmax(logits, dim=-1).numpy()

    results = {}
    for i, ticker in enumerate(valid_tickers):
        down, flat, up = float(probs[i][0]), float(probs[i][1]), float(probs[i][2])
        direction = "up" if up > down and up > flat else ("down" if down > up and down > flat else "flat")
        score = up - down  # range [-1, 1]
        results[ticker] = {"score": round(score, 4), "direction": direction, "probs": [down, flat, up]}

    return results
