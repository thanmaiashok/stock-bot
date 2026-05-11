"""
Neo4j graph builder. Sparse sector-partitioned correlation graph.
Nodes: Stock, Sector, NewsEvent, Company
Relationships: BELONGS_TO, CORRELATES_WITH, MENTIONS, COMPETES_WITH
"""

import json
import logging
from datetime import datetime, timezone

import pandas as pd
from neo4j import GraphDatabase

import database
from config import (
    NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD,
    CORRELATION_THRESHOLD, MAX_CROSS_SECTOR_PAIRS,
)

logger = logging.getLogger(__name__)


def get_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def init_graph():
    """Create constraints and indexes."""
    with get_driver() as drv:
        with drv.session() as sess:
            sess.run("CREATE CONSTRAINT IF NOT EXISTS FOR (s:Stock) REQUIRE s.ticker IS UNIQUE")
            sess.run("CREATE CONSTRAINT IF NOT EXISTS FOR (s:Sector) REQUIRE s.name IS UNIQUE")
            sess.run("CREATE CONSTRAINT IF NOT EXISTS FOR (n:NewsEvent) REQUIRE n.url_hash IS UNIQUE")
            sess.run("CREATE INDEX IF NOT EXISTS FOR (s:Stock) ON (s.exchange)")
    logger.info("Neo4j graph initialized")


def sync_stocks_and_sectors():
    """Upsert Stock and Sector nodes from ticker_universe."""
    conn = database.get_connection()
    try:
        rows = conn.execute(
            "SELECT ticker, exchange, name, sector FROM ticker_universe WHERE active=1 AND tier>=1"
        ).fetchall()
    finally:
        conn.close()

    with get_driver() as drv:
        with drv.session() as sess:
            batch = [{"ticker": r["ticker"], "exchange": r["exchange"],
                      "name": r["name"] or r["ticker"],
                      "sector": r["sector"] or "Unknown"} for r in rows]

            sess.run("""
                UNWIND $batch AS s
                MERGE (stock:Stock {ticker: s.ticker})
                SET stock.exchange = s.exchange, stock.name = s.name
                MERGE (sec:Sector {name: s.sector})
                MERGE (stock)-[:BELONGS_TO]->(sec)
            """, batch=batch)
    logger.info("Synced %d stock nodes to Neo4j", len(rows))


def update_correlations():
    """
    Compute price correlations — within sector only + top cross-sector pairs.
    Uses 90d daily close prices from SQLite.
    """
    conn = database.get_connection()
    try:
        rows = conn.execute("""
            SELECT p.ticker, p.date, p.close, u.sector
            FROM price_history p
            JOIN ticker_universe u ON p.ticker=u.ticker
            WHERE p.interval='1d'
              AND u.active=1 AND u.tier>=1
              AND p.date >= date('now', '-90 days')
        """).fetchall()
    finally:
        conn.close()

    if not rows:
        logger.warning("No price data for correlation computation")
        return

    df = pd.DataFrame(rows, columns=["ticker", "date", "close", "sector"])
    pivot = df.pivot_table(index="date", columns="ticker", values="close")
    returns = pivot.pct_change().dropna(how="all")

    sectors = df.drop_duplicates("ticker").set_index("ticker")["sector"].to_dict()
    tickers = list(returns.columns)

    corr_pairs = []

    # Within-sector correlations
    sector_groups: dict[str, list[str]] = {}
    for t in tickers:
        s = sectors.get(t, "Unknown")
        sector_groups.setdefault(s, []).append(t)

    for sector, members in sector_groups.items():
        if len(members) < 2:
            continue
        sub = returns[members].dropna(how="all")
        corr_matrix = sub.corr()
        for i, t1 in enumerate(members):
            for t2 in members[i + 1:]:
                try:
                    c = float(corr_matrix.loc[t1, t2])
                    if c >= CORRELATION_THRESHOLD:
                        corr_pairs.append((t1, t2, round(c, 4)))
                except Exception:
                    pass

    # Top cross-sector by abs correlation (limit per ticker)
    if len(tickers) <= 500:  # Only feasible for smaller sets
        full_corr = returns.corr()
        for t in tickers:
            if t not in full_corr.index:
                continue
            t_sector = sectors.get(t, "Unknown")
            cross = [(other, abs(float(full_corr.loc[t, other])))
                     for other in tickers
                     if other != t and sectors.get(other, "Unknown") != t_sector
                     and not pd.isna(full_corr.loc[t, other])]
            cross.sort(key=lambda x: x[1], reverse=True)
            for other, c in cross[:MAX_CROSS_SECTOR_PAIRS]:
                if c >= CORRELATION_THRESHOLD:
                    pair = tuple(sorted([t, other]))
                    corr_pairs.append((pair[0], pair[1], round(c, 4)))

    # Deduplicate
    seen = set()
    unique_pairs = []
    for t1, t2, c in corr_pairs:
        key = tuple(sorted([t1, t2]))
        if key not in seen:
            seen.add(key)
            unique_pairs.append({"t1": t1, "t2": t2, "weight": c})

    if not unique_pairs:
        logger.info("No correlations above threshold %.2f", CORRELATION_THRESHOLD)
        return

    with get_driver() as drv:
        with drv.session() as sess:
            # Clear old correlations
            sess.run("MATCH ()-[r:CORRELATES_WITH]->() DELETE r")
            # Batch insert new
            CHUNK = 1000
            for i in range(0, len(unique_pairs), CHUNK):
                chunk = unique_pairs[i: i + CHUNK]
                sess.run("""
                    UNWIND $pairs AS p
                    MATCH (a:Stock {ticker: p.t1})
                    MATCH (b:Stock {ticker: p.t2})
                    MERGE (a)-[r:CORRELATES_WITH]-(b)
                    SET r.weight = p.weight
                """, pairs=chunk)

    logger.info("Updated %d correlation edges in Neo4j", len(unique_pairs))


def add_news_events():
    """Link recent news articles to mentioned stocks."""
    conn = database.get_connection()
    try:
        rows = conn.execute("""
            SELECT url_hash, headline, published_at, ticker_mentions
            FROM news_articles
            WHERE published_at >= date('now', '-7 days')
            ORDER BY published_at DESC LIMIT 5000
        """).fetchall()
    finally:
        conn.close()

    events = []
    for row in rows:
        mentions = json.loads(row["ticker_mentions"] or "[]")
        if mentions:
            events.append({
                "url_hash": row["url_hash"],
                "headline": row["headline"][:200],
                "published_at": row["published_at"],
                "mentions": mentions,
            })

    if not events:
        return

    with get_driver() as drv:
        with drv.session() as sess:
            CHUNK = 500
            for i in range(0, len(events), CHUNK):
                chunk = events[i: i + CHUNK]
                sess.run("""
                    UNWIND $events AS e
                    MERGE (n:NewsEvent {url_hash: e.url_hash})
                    SET n.headline = e.headline, n.published_at = e.published_at
                    WITH n, e
                    UNWIND e.mentions AS symbol
                    MATCH (s:Stock) WHERE s.ticker STARTS WITH symbol
                    MERGE (n)-[:MENTIONS]->(s)
                """, events=chunk)

    logger.info("Synced %d news events to Neo4j", len(events))


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def get_correlated_stocks(ticker: str, limit: int = 20) -> list[dict]:
    with get_driver() as drv:
        with drv.session() as sess:
            result = sess.run("""
                MATCH (a:Stock {ticker: $ticker})-[r:CORRELATES_WITH]-(b:Stock)
                RETURN b.ticker AS ticker, b.name AS name, r.weight AS weight
                ORDER BY r.weight DESC LIMIT $limit
            """, ticker=ticker, limit=limit)
            return [dict(r) for r in result]


def get_sector_stocks(sector: str) -> list[dict]:
    with get_driver() as drv:
        with drv.session() as sess:
            result = sess.run("""
                MATCH (s:Stock)-[:BELONGS_TO]->(sec:Sector {name: $sector})
                RETURN s.ticker AS ticker, s.name AS name, s.exchange AS exchange
            """, sector=sector)
            return [dict(r) for r in result]


def get_news_for_stock(ticker: str, limit: int = 20) -> list[dict]:
    with get_driver() as drv:
        with drv.session() as sess:
            result = sess.run("""
                MATCH (n:NewsEvent)-[:MENTIONS]->(s:Stock {ticker: $ticker})
                RETURN n.headline AS headline, n.published_at AS published_at
                ORDER BY n.published_at DESC LIMIT $limit
            """, ticker=ticker, limit=limit)
            return [dict(r) for r in result]


def get_market_graph(top_corr_per_node: int = 4) -> dict:
    """
    Full market map: all Tier 2 stocks as nodes, strongest correlation edges.
    Falls back to same-sector grouping if Neo4j empty.
    Used as default Bloomberg-style overview.
    """
    import database as db
    import numpy as np

    conn = db.get_connection()
    try:
        # All Tier 2 stocks with latest signal
        rows = conn.execute("""
            SELECT tu.ticker, tu.name, tu.exchange, tu.sector,
                   s.signal, s.confidence
            FROM ticker_universe tu
            LEFT JOIN (
                SELECT ticker, signal, confidence FROM signals
                WHERE (ticker, timestamp) IN (
                    SELECT ticker, MAX(timestamp) FROM signals GROUP BY ticker
                )
            ) s ON tu.ticker = s.ticker
            WHERE tu.tier = 2 AND tu.active = 1
        """).fetchall()
    finally:
        conn.close()

    if not rows:
        return {"nodes": [], "links": []}

    tickers = [r["ticker"] for r in rows]
    ticker_set = set(tickers)

    nodes = []
    for r in rows:
        nodes.append({
            "id": r["ticker"],
            "type": "stock",
            "label": r["ticker"],
            "name": r["name"] or r["ticker"],
            "exchange": r["exchange"] or "",
            "sector": r["sector"] or "Unknown",
            "signal": r["signal"] or "HOLD",
            "confidence": float(r["confidence"] or 0),
        })

    links = []
    seen_pairs = set()

    # 1. Real correlations from SQLite price_correlations (computed by compute_price_correlations)
    conn2 = db.get_connection()
    try:
        corr_rows = conn2.execute("""
            SELECT ticker1, ticker2, correlation FROM price_correlations
            WHERE ABS(correlation) >= 0.50
            ORDER BY ABS(correlation) DESC
            LIMIT 600
        """).fetchall()
    finally:
        conn2.close()

    if corr_rows:
        for r in corr_rows:
            if r["ticker1"] in ticker_set and r["ticker2"] in ticker_set:
                links.append({"source": r["ticker1"], "target": r["ticker2"],
                               "type": "CORRELATES_WITH", "weight": round(float(r["correlation"]), 3)})
                seen_pairs.add((r["ticker1"], r["ticker2"]))

    # 2. Fallback: Neo4j
    if not links:
        try:
            with get_driver() as drv:
                with drv.session() as sess:
                    result = sess.run("""
                        MATCH (a:Stock)-[r:CORRELATES_WITH]-(b:Stock)
                        WHERE a.ticker IN $tickers AND b.ticker IN $tickers
                          AND r.weight >= 0.60
                        RETURN a.ticker AS t1, b.ticker AS t2, r.weight AS w
                        ORDER BY r.weight DESC LIMIT 500
                    """, tickers=tickers)
                    for rec in result:
                        pair = tuple(sorted([rec["t1"], rec["t2"]]))
                        if pair not in seen_pairs:
                            seen_pairs.add(pair)
                            links.append({"source": rec["t1"], "target": rec["t2"],
                                          "type": "CORRELATES_WITH", "weight": float(rec["w"])})
        except Exception:
            pass

    # 3. Last resort: sector grouping
    if not links:
        from collections import defaultdict
        sector_map = defaultdict(list)
        for r in rows:
            sector_map[r["sector"] or r["exchange"] or "OTHER"].append(r["ticker"])
        for _, members in sector_map.items():
            for i, t1 in enumerate(members):
                for t2 in members[i+1: i+1+top_corr_per_node]:
                    pair = tuple(sorted([t1, t2]))
                    if pair not in seen_pairs:
                        seen_pairs.add(pair)
                        links.append({"source": t1, "target": t2,
                                      "type": "CORRELATES_WITH", "weight": 0.70})

    return {"nodes": nodes, "links": links}


def get_knowledge_graph(ticker: str, corr_limit: int = 15, news_limit: int = 8) -> dict:
    """
    Full knowledge graph around a ticker.
    Nodes: Stock, Sector, News. Edges: CORRELATES_WITH, BELONGS_TO, MENTIONS.
    Falls back to SQLite if Neo4j is empty/unavailable.
    """
    import database as db
    import json as _json

    ticker = ticker.upper()
    nodes: dict[str, dict] = {}
    links: list[dict] = []

    # --- Center stock info from SQLite ---
    conn = db.get_connection()
    try:
        center = conn.execute(
            "SELECT ticker, name, exchange, sector FROM ticker_universe WHERE ticker=?", (ticker,)
        ).fetchone()
        sig = conn.execute(
            "SELECT signal, confidence FROM signals WHERE ticker=? ORDER BY timestamp DESC LIMIT 1", (ticker,)
        ).fetchone()
        nodes[ticker] = {
            "id": ticker, "type": "stock", "label": ticker,
            "name": center["name"] if center else ticker,
            "exchange": center["exchange"] if center else "",
            "signal": sig["signal"] if sig else "HOLD",
            "confidence": float(sig["confidence"]) if sig else 0.0,
            "isCenter": True,
        }

        # Sector node
        sector = center["sector"] if center else None
        if sector:
            sec_id = f"sector:{sector}"
            nodes[sec_id] = {"id": sec_id, "type": "sector", "label": sector}
            links.append({"source": ticker, "target": sec_id, "type": "BELONGS_TO"})

        # Recent news: try ticker-specific first, fall back to recent any-news
        base = ticker.split(".")[0]
        news_rows = conn.execute("""
            SELECT id, headline, published_at FROM news_articles
            WHERE ticker_mentions LIKE ?
            ORDER BY published_at DESC LIMIT ?
        """, (f'%{base}%', news_limit)).fetchall()
        if not news_rows:
            news_rows = conn.execute("""
                SELECT id, headline, published_at FROM news_articles
                ORDER BY published_at DESC LIMIT ?
            """, (news_limit,)).fetchall()
        for n in news_rows:
            nid = f"news:{n['id']}"
            headline = (n["headline"] or "")[:60]
            nodes[nid] = {"id": nid, "type": "news", "label": headline, "published_at": n["published_at"]}
            links.append({"source": nid, "target": ticker, "type": "MENTIONS"})

        # Correlated stocks: same sector first, then Tier 2 peers as fallback
        sqlite_corrs = []
        if sector:
            same_sector = conn.execute("""
                SELECT tu.ticker, tu.name, s.signal, s.confidence
                FROM ticker_universe tu
                LEFT JOIN (
                    SELECT ticker, signal, confidence FROM signals
                    WHERE (ticker, timestamp) IN (SELECT ticker, MAX(timestamp) FROM signals GROUP BY ticker)
                ) s ON tu.ticker = s.ticker
                WHERE tu.sector=? AND tu.ticker!=? AND tu.active=1 AND tu.tier>=1
                LIMIT ?
            """, (sector, ticker, corr_limit)).fetchall()
            for r in same_sector:
                sqlite_corrs.append({"ticker": r["ticker"], "name": r["name"],
                                     "signal": r["signal"], "confidence": r["confidence"], "weight": 0.75})

        if not sqlite_corrs:
            # Fallback: other Tier 2 stocks on same exchange
            t2_peers = conn.execute("""
                SELECT tu.ticker, tu.name, tu.exchange, s.signal, s.confidence
                FROM ticker_universe tu
                LEFT JOIN (
                    SELECT ticker, signal, confidence FROM signals
                    WHERE (ticker, timestamp) IN (SELECT ticker, MAX(timestamp) FROM signals GROUP BY ticker)
                ) s ON tu.ticker = s.ticker
                WHERE tu.tier=2 AND tu.ticker!=? AND tu.active=1
                ORDER BY s.confidence DESC NULLS LAST
                LIMIT ?
            """, (ticker, corr_limit)).fetchall()
            for r in t2_peers:
                sqlite_corrs.append({"ticker": r["ticker"], "name": r["name"],
                                     "signal": r["signal"], "confidence": r["confidence"], "weight": 0.6})
    finally:
        conn.close()

    # Try Neo4j for real correlations (override SQLite if available)
    try:
        neo_corrs = get_correlated_stocks(ticker, corr_limit)
        neo_news = get_news_for_stock(ticker, news_limit)
        if neo_corrs:
            # Use Neo4j correlations instead
            for c in neo_corrs:
                ct = c["ticker"]
                conn2 = db.get_connection()
                try:
                    sig2 = conn2.execute(
                        "SELECT signal, confidence FROM signals WHERE ticker=? ORDER BY timestamp DESC LIMIT 1", (ct,)
                    ).fetchone()
                finally:
                    conn2.close()
                nodes[ct] = {
                    "id": ct, "type": "stock", "label": ct,
                    "name": c.get("name") or ct,
                    "signal": sig2["signal"] if sig2 else "HOLD",
                    "confidence": float(sig2["confidence"]) if sig2 else 0.0,
                    "weight": float(c.get("weight") or 0.75),
                }
                links.append({"source": ticker, "target": ct, "type": "CORRELATES_WITH", "weight": float(c.get("weight") or 0.75)})

            # Neo4j news (add on top, deduplicate by label)
            existing_labels = {n["label"] for n in nodes.values() if n["type"] == "news"}
            for n in neo_news:
                headline = (n.get("headline") or "")[:60]
                if headline not in existing_labels:
                    nid = f"news:neo:{headline[:20]}"
                    nodes[nid] = {"id": nid, "type": "news", "label": headline, "published_at": n.get("published_at")}
                    links.append({"source": nid, "target": ticker, "type": "MENTIONS"})
                    existing_labels.add(headline)
        else:
            # Use SQLite same-sector fallback
            for c in sqlite_corrs:
                ct = c["ticker"]
                if ct not in nodes:
                    nodes[ct] = {
                        "id": ct, "type": "stock", "label": ct,
                        "name": c.get("name") or ct,
                        "signal": c.get("signal") or "HOLD",
                        "confidence": float(c.get("confidence") or 0),
                        "weight": c["weight"],
                    }
                    links.append({"source": ticker, "target": ct, "type": "CORRELATES_WITH", "weight": c["weight"]})
    except Exception:
        # Full SQLite fallback
        for c in sqlite_corrs:
            ct = c["ticker"]
            if ct not in nodes:
                nodes[ct] = {
                    "id": ct, "type": "stock", "label": ct,
                    "name": c.get("name") or ct,
                    "signal": c.get("signal") or "HOLD",
                    "confidence": float(c.get("confidence") or 0),
                    "weight": c["weight"],
                }
                links.append({"source": ticker, "target": ct, "type": "CORRELATES_WITH", "weight": c["weight"]})

    return {"center": ticker, "nodes": list(nodes.values()), "links": links}


def run_full_graph_update():
    sync_stocks_and_sectors()
    update_correlations()
    add_news_events()
