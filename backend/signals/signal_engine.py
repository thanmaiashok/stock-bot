"""
Signal engine: combines GNN + XGBoost + Sentiment + Fundamentals + Insider + Patterns.
Fear & Greed Index used as confidence multiplier (market regime filter).
Runs on Tier 2 tickers only.
"""

import json
import logging
from datetime import datetime, timezone

import numpy as np

import database
from config import (
    GNN_WEIGHT, XGB_WEIGHT, SENTIMENT_WEIGHT, FUNDAMENTAL_WEIGHT, PATTERN_WEIGHT,
    INSIDER_WEIGHT, SIGNAL_CONFIDENCE_THRESHOLD,
)
from data.universe_manager import get_tickers_by_tier
from signals.technical_features import compute_technicals, technical_signal_score
from data.sentiment_scorer import get_sentiment

logger = logging.getLogger(__name__)

_xgb_model = None


def _load_xgb_model():
    global _xgb_model
    if _xgb_model is not None:
        return _xgb_model
    import os
    model_path = os.path.join(os.path.dirname(__file__), "..", "models", "xgb_model.json")
    try:
        import xgboost as xgb
        if os.path.exists(model_path):
            m = xgb.XGBClassifier()
            m.load_model(model_path)
            _xgb_model = m
            logger.info("XGBoost model loaded")
        else:
            logger.info("XGBoost model not trained yet — training now")
            _xgb_model = _train_xgb(model_path)
    except Exception as exc:
        logger.warning("XGBoost load failed: %s", exc)
    return _xgb_model


def _train_xgb(model_path: str):
    """Train XGBoost on technical features from all Tier 1+2 tickers."""
    import xgboost as xgb
    import pandas as pd
    import os

    conn = database.get_connection()
    try:
        tickers = [r["ticker"] for r in conn.execute(
            "SELECT ticker FROM ticker_universe WHERE active=1 AND tier>=1"
        ).fetchall()]
    finally:
        conn.close()

    X, y = [], []
    for ticker in tickers:
        try:
            tech = compute_technicals(ticker)
            if not tech:
                continue
            score, _ = technical_signal_score(tech)

            conn = database.get_connection()
            try:
                rows = conn.execute("""
                    SELECT close FROM price_history
                    WHERE ticker=? AND interval='1d' ORDER BY date DESC LIMIT 3
                """, (ticker,)).fetchall()
            finally:
                conn.close()

            if len(rows) < 2:
                continue
            pct = (rows[0]["close"] - rows[1]["close"]) / (rows[1]["close"] + 1e-9)
            label = 2 if pct > 0.005 else (0 if pct < -0.005 else 1)

            features = [
                tech.get("rsi", 50) or 50,
                tech.get("rsi_fast", 50) or 50,
                tech.get("stoch", 50) or 50,
                tech.get("williams_r", -50) or -50,
                tech.get("macd", 0) or 0,
                tech.get("macd_hist", 0) or 0,
                tech.get("adx", 0) or 0,
                tech.get("cci", 0) or 0,
                tech.get("mfi", 50) or 50,
                tech.get("bb_pband", 0.5) or 0.5,
                tech.get("bb_wband", 0) or 0,
                tech.get("price_change_pct", 0) or 0,
                tech.get("roc", 0) or 0,
                score,
            ]
            X.append(features)
            y.append(label)
        except Exception:
            pass

    if len(X) < 20:
        logger.warning("Not enough data to train XGBoost (%d samples)", len(X))
        return None

    model = xgb.XGBClassifier(n_estimators=100, max_depth=4, learning_rate=0.1,
                               use_label_encoder=False, eval_metric="mlogloss")
    model.fit(np.array(X), np.array(y))
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    model.save_model(model_path)
    logger.info("XGBoost trained on %d samples, saved to %s", len(X), model_path)
    return model


def _xgb_score(ticker: str) -> float:
    """Returns score in [-1, 1]. Positive = bullish."""
    model = _load_xgb_model()
    if model is None:
        return 0.0
    try:
        import numpy as np
        tech = compute_technicals(ticker)
        if not tech:
            return 0.0
        ts, _ = technical_signal_score(tech)
        features = np.array([[
            tech.get("rsi", 50) or 50,
            tech.get("rsi_fast", 50) or 50,
            tech.get("stoch", 50) or 50,
            tech.get("williams_r", -50) or -50,
            tech.get("macd", 0) or 0,
            tech.get("macd_hist", 0) or 0,
            tech.get("adx", 0) or 0,
            tech.get("cci", 0) or 0,
            tech.get("mfi", 50) or 50,
            tech.get("bb_pband", 0.5) or 0.5,
            tech.get("bb_wband", 0) or 0,
            tech.get("price_change_pct", 0) or 0,
            tech.get("roc", 0) or 0,
            ts,
        ]])
        probs = model.predict_proba(features)[0]  # [down, flat, up]
        return float(probs[2] - probs[0])
    except Exception as exc:
        logger.debug("XGB score failed for %s: %s", ticker, exc)
        return 0.0


def _sentiment_score(ticker: str) -> float:
    """Returns composite sentiment in [-1, 1]."""
    data = get_sentiment(ticker, days=3)
    if not data:
        return 0.0
    return float(data[0]["composite_score"])


def _fundamental_score(ticker: str) -> tuple[float, list[str]]:
    """Returns score in [-1, 1] and reasons."""
    conn = database.get_connection()
    try:
        row = conn.execute(
            "SELECT pe_ratio, eps, roe, debt_to_equity, profit_margin FROM fundamentals WHERE ticker=?",
            (ticker,)
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return 0.0, []

    score = 0.0
    reasons = []

    if row["roe"] is not None:
        if row["roe"] > 0.15:
            score += 0.5
            reasons.append(f"Strong ROE {row['roe']:.1%}")
        elif row["roe"] < 0:
            score -= 0.5
            reasons.append(f"Negative ROE {row['roe']:.1%}")

    if row["debt_to_equity"] is not None:
        if row["debt_to_equity"] < 0.5:
            score += 0.3
            reasons.append("Low debt/equity")
        elif row["debt_to_equity"] > 2.0:
            score -= 0.3
            reasons.append(f"High D/E {row['debt_to_equity']:.1f}")

    if row["profit_margin"] is not None:
        if row["profit_margin"] > 0.15:
            score += 0.2
            reasons.append(f"Margin {row['profit_margin']:.1%}")
        elif row["profit_margin"] < 0:
            score -= 0.3
            reasons.append("Negative margin")

    return max(-1.0, min(1.0, score)), reasons


def _insider_score(ticker: str) -> float:
    """Insider trading signal from SEC Form 4. Score in [-1, 1]."""
    try:
        from data.insider_fetcher import get_insider_score
        return get_insider_score(ticker)
    except Exception as exc:
        logger.debug("Insider score failed for %s: %s", ticker, exc)
        return 0.0


def _pattern_score(ticker: str) -> tuple[float, list[str]]:
    """Returns pattern score in [-1, 1] and active pattern labels."""
    try:
        from signals.pattern_engine import scan_patterns
        result = scan_patterns(ticker)
        raw = result.get("pattern_score", 0.0)  # [0, 1]
        # Map [0,1] → [-1,1]: >0.5 = bullish, <0.5 = bearish-neutral
        score = (raw - 0.5) * 2.0
        labels = result.get("patterns", [])
        stage = result.get("stage", {})
        if stage.get("stage") == 4:
            score = min(score, -0.3)  # Stage 4 = downtrend, cap positive
            labels.append("STAGE4_AVOID")
        return round(score, 4), labels
    except Exception as exc:
        logger.debug("Pattern score failed for %s: %s", ticker, exc)
        return 0.0, []


def generate_signal(ticker: str, gnn_predictions: dict) -> dict | None:
    """Generate signal for a single ticker."""
    try:
        tech = compute_technicals(ticker)
        if not tech:
            return None

        tech_raw, tech_reasons = technical_signal_score(tech)
        xgb_raw = _xgb_score(ticker)
        sent_raw = _sentiment_score(ticker)
        fund_raw, fund_reasons = _fundamental_score(ticker)
        pat_raw, pat_labels = _pattern_score(ticker)
        insider_raw = _insider_score(ticker)

        gnn_data = gnn_predictions.get(ticker, {})
        gnn_raw = gnn_data.get("score", 0.0)
        gnn_reasons = [f"GNN: {gnn_data.get('direction', 'flat')} ({gnn_raw:+.2f})"]

        # Weighted composite score in [-1, 1]
        composite = (
            gnn_raw * GNN_WEIGHT +
            xgb_raw * XGB_WEIGHT +
            sent_raw * SENTIMENT_WEIGHT +
            fund_raw * FUNDAMENTAL_WEIGHT +
            pat_raw * PATTERN_WEIGHT +
            insider_raw * INSIDER_WEIGHT
        )

        # Market regime multipliers (Fear&Greed + Breadth + Macro) — cascade on BUY signals
        try:
            from signals.fear_greed import get_fear_greed_multiplier
            from signals.market_breadth import get_breadth_multiplier
            from data.macro_fetcher import get_macro_regime
            fg_mult = get_fear_greed_multiplier()
            breadth_mult = get_breadth_multiplier()
            macro_mult = get_macro_regime().get("signal_mult", 1.0)
            combined_mult = fg_mult * breadth_mult * macro_mult
            # Only apply multiplier to BUY direction
            if composite > 0:
                composite = composite * combined_mult
        except Exception:
            pass

        # Map to signal + confidence
        abs_score = abs(composite)
        confidence = round(min(abs_score, 1.0), 4)
        signal = "BUY" if composite > 0.1 else ("SELL" if composite < -0.1 else "HOLD")

        all_reasons = tech_reasons + fund_reasons + gnn_reasons
        if sent_raw > 0.2:
            all_reasons.append(f"Positive sentiment ({sent_raw:+.2f})")
        elif sent_raw < -0.2:
            all_reasons.append(f"Negative sentiment ({sent_raw:+.2f})")
        if pat_labels:
            all_reasons.append(f"Patterns: {', '.join(pat_labels)}")
        if insider_raw > 0.2:
            all_reasons.append(f"Insider buying (SEC Form 4, score={insider_raw:+.2f})")
        elif insider_raw < -0.2:
            all_reasons.append(f"Insider selling ({insider_raw:+.2f})")

        conn = database.get_connection()
        try:
            conn.execute("""
                INSERT INTO signals
                    (ticker, timestamp, signal, confidence, gnn_score, xgb_score,
                     sentiment_score, fundamental_score, reasons, tier, price)
                VALUES (?,?,?,?,?,?,?,?,?,2,?)
            """, (
                ticker,
                datetime.now(timezone.utc).isoformat(),
                signal, confidence,
                round(gnn_raw, 4), round(xgb_raw, 4),
                round(sent_raw, 4), round(fund_raw, 4),
                json.dumps(all_reasons),
                tech.get("current_price"),
            ))
            conn.commit()
        finally:
            conn.close()

        return {
            "ticker": ticker,
            "signal": signal,
            "confidence": confidence,
            "price": tech.get("current_price"),
            "rsi": tech.get("rsi"),
            "atr": tech.get("atr"),
            "gnn_score": round(gnn_raw, 4),
            "xgb_score": round(xgb_raw, 4),
            "sentiment_score": round(sent_raw, 4),
            "fundamental_score": round(fund_raw, 4),
            "pattern_score": round(pat_raw, 4),
            "patterns": pat_labels,
            "reasons": all_reasons,
        }
    except Exception as exc:
        logger.error("Signal generation failed for %s: %s", ticker, exc)
        return None


def run_signal_generation():
    """Run full signal generation for all Tier 2 tickers."""
    tickers = get_tickers_by_tier(2)
    if not tickers:
        logger.warning("No Tier 2 tickers available for signal generation")
        return

    logger.info("Generating signals for %d Tier 2 tickers", len(tickers))

    # Batch GNN inference
    try:
        from graph.gnn_model import predict as gnn_predict
        gnn_predictions = gnn_predict(tickers)
    except Exception as exc:
        logger.warning("GNN inference failed: %s — using empty predictions", exc)
        gnn_predictions = {}

    results = []
    for ticker in tickers:
        sig = generate_signal(ticker, gnn_predictions)
        if sig:
            results.append(sig)

    buy_count = sum(1 for s in results if s["signal"] == "BUY")
    sell_count = sum(1 for s in results if s["signal"] == "SELL")
    hold_count = sum(1 for s in results if s["signal"] == "HOLD")
    logger.info("Signals: BUY=%d SELL=%d HOLD=%d (of %d total)",
                buy_count, sell_count, hold_count, len(results))

    # Adaptive fetch: hot signals (confidence >40%) get fresh price data immediately
    hot = [s["ticker"] for s in results if s["confidence"] > 0.40]
    if hot:
        logger.info("Signal-triggered fetch for %d hot tickers: %s", len(hot), hot[:5])
        try:
            from data.market_fetcher import fetch_tickers_now
            fetch_tickers_now(hot)
        except Exception as exc:
            logger.debug("Hot fetch failed: %s", exc)

    return results
