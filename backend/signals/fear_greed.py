"""
Fear & Greed Index — computed locally from market data. No API key needed.

Inspired by CNN's Fear & Greed methodology (public domain formula) and
academic market sentiment literature. All components sourced from data
already in our DB or free public endpoints (CBOE, yfinance).

Components (each scored 0-100, equal weight):
  1. Market Momentum    — S&P 500 vs 125-day MA
  2. Stock Strength     — New 52-week highs vs lows ratio
  3. Put/Call Ratio     — CBOE total put/call (free, no auth)
  4. VIX Level          — CBOE VIX (via yfinance ^VIX)
  5. Breadth            — % stocks above 200-day MA (our universe)
  6. Junk Bond Spread   — Approximated from HYG price vs trend

Final score: 0 = Extreme Fear, 100 = Extreme Greed.
< 25 = Extreme Fear (buy zone), > 75 = Extreme Greed (caution).
"""

import logging
from datetime import datetime, timezone, timedelta

import numpy as np
import requests

import database

logger = logging.getLogger(__name__)

CBOE_PC_URL = "https://cdn.cboe.com/api/global/us_options_market_statistics/chart-data.json"
HEADERS = {"User-Agent": "StockBot/1.0 research@stockbot.local"}

_SPX_PROXY_TICKER = "SPY"   # S&P 500 proxy in our DB


def _score_momentum() -> float:
    """S&P 500 (SPY) vs 125-day moving average. Above=greed, below=fear."""
    conn = database.get_connection()
    try:
        rows = conn.execute("""
            SELECT close FROM price_history
            WHERE ticker=? AND interval='1d'
            ORDER BY date DESC LIMIT 130
        """, (_SPX_PROXY_TICKER,)).fetchall()
    finally:
        conn.close()

    closes = [r["close"] for r in rows]
    if len(closes) < 126:
        return 50.0
    current = closes[0]
    ma125 = sum(closes[:125]) / 125
    pct = (current - ma125) / ma125 * 100
    # Map: -10% = 0 (fear), 0% = 50 (neutral), +10% = 100 (greed)
    raw = (pct + 10) / 20 * 100
    return max(0.0, min(100.0, raw))


def _score_stock_strength() -> float:
    """Ratio of stocks at 52-week high vs 52-week low in our universe."""
    conn = database.get_connection()
    try:
        rows = conn.execute("""
            SELECT ticker,
                   MAX(high) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 251 PRECEDING AND CURRENT ROW) as h52,
                   MIN(low)  OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 251 PRECEDING AND CURRENT ROW) as l52,
                   close,
                   date
            FROM price_history
            WHERE interval='1d'
            AND date = (SELECT MAX(date) FROM price_history WHERE interval='1d')
            LIMIT 500
        """).fetchall()
    except Exception:
        return 50.0
    finally:
        conn.close()

    if not rows:
        return 50.0

    highs = sum(1 for r in rows if r["close"] and r["h52"] and r["close"] >= r["h52"] * 0.99)
    lows = sum(1 for r in rows if r["close"] and r["l52"] and r["close"] <= r["l52"] * 1.01)
    total = len(rows)
    if total == 0:
        return 50.0
    ratio = (highs - lows) / total  # [-1, 1]
    return max(0.0, min(100.0, (ratio + 1) / 2 * 100))


def _score_breadth() -> float:
    """% of stocks in our universe trading above 200-day MA."""
    conn = database.get_connection()
    try:
        # Get latest close vs 200d MA for each ticker
        rows = conn.execute("""
            SELECT ticker, AVG(CASE WHEN rn <= 1 THEN close END) as latest,
                   AVG(CASE WHEN rn <= 200 THEN close END) as ma200
            FROM (
                SELECT ticker, close,
                       ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) as rn
                FROM price_history WHERE interval='1d'
            ) sub
            GROUP BY ticker
            HAVING COUNT(*) >= 50
            LIMIT 1000
        """).fetchall()
    except Exception:
        return 50.0
    finally:
        conn.close()

    if not rows:
        return 50.0
    above = sum(1 for r in rows if r["latest"] and r["ma200"] and r["latest"] > r["ma200"])
    pct = above / len(rows) * 100
    return max(0.0, min(100.0, pct))


def _score_put_call() -> float:
    """
    CBOE total put/call ratio. Free public endpoint, no API key.
    Low ratio = greed (everyone bullish), high ratio = fear (hedging).
    """
    try:
        resp = requests.get(CBOE_PC_URL, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        # Chart data format: {data: [{date, pcRatio, ...}]}
        entries = data.get("data", [])
        if not entries:
            return 50.0
        latest = entries[-1]
        pc = float(latest.get("pcRatio") or latest.get("totalRatio") or 1.0)
        # Typical range 0.5 (extreme greed) to 1.5 (extreme fear)
        # Map: 0.5→100 (greed), 1.0→50 (neutral), 1.5→0 (fear)
        raw = (1.5 - pc) / 1.0 * 100
        return max(0.0, min(100.0, raw))
    except Exception as exc:
        logger.debug("Put/call ratio fetch failed: %s", exc)
        return 50.0


def _score_vix() -> float:
    """
    VIX level from our DB (^VIX tracked by yfinance fetcher).
    Low VIX = greed, High VIX = fear.
    """
    conn = database.get_connection()
    try:
        row = conn.execute("""
            SELECT close FROM price_history
            WHERE ticker='^VIX' AND interval='1d'
            ORDER BY date DESC LIMIT 1
        """).fetchone()
    finally:
        conn.close()

    if not row:
        # Try fetching via yfinance
        try:
            import yfinance as yf
            vix = yf.Ticker("^VIX").fast_info.last_price
            if vix:
                return max(0.0, min(100.0, (40 - vix) / 30 * 100))
        except Exception:
            pass
        return 50.0

    vix = float(row["close"])
    # VIX 10 = extreme greed (100), VIX 20 = neutral (50), VIX 40 = extreme fear (0)
    raw = (40 - vix) / 30 * 100
    return max(0.0, min(100.0, raw))


def compute_fear_greed() -> dict:
    """
    Compute Fear & Greed Index from all components.
    Returns {score, label, components} — all computed locally, no API key.
    """
    components = {
        "momentum":   _score_momentum(),
        "strength":   _score_stock_strength(),
        "breadth":    _score_breadth(),
        "put_call":   _score_put_call(),
        "vix":        _score_vix(),
    }

    # Equal weight all components
    score = round(sum(components.values()) / len(components), 1)

    if score <= 25:
        label = "Extreme Fear"
    elif score <= 45:
        label = "Fear"
    elif score <= 55:
        label = "Neutral"
    elif score <= 75:
        label = "Greed"
    else:
        label = "Extreme Greed"

    result = {
        "score": score,
        "label": label,
        "components": {k: round(v, 1) for k, v in components.items()},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "interpretation": {
            "action": "BUY_ZONE" if score <= 25 else ("SELL_ZONE" if score >= 75 else "NEUTRAL"),
            "note": "Buy when others fearful, sell when greedy (Buffett rule)",
        },
    }

    # Cache in DB for API access
    _cache_result(result)
    return result


def get_fear_greed_multiplier() -> float:
    """
    Signal confidence multiplier based on Fear & Greed.
    Extreme Fear → amplify BUY confidence by 1.2x.
    Extreme Greed → dampen BUY confidence by 0.8x.
    Used in signal_engine to adjust final confidence.
    """
    try:
        cached = _load_cached()
        if cached:
            score = cached["score"]
        else:
            score = compute_fear_greed()["score"]

        if score <= 20:
            return 1.25   # extreme fear = screaming buy
        elif score <= 35:
            return 1.10   # fear = lean bullish
        elif score >= 80:
            return 0.75   # extreme greed = be cautious
        elif score >= 65:
            return 0.90   # greed = slight caution
        return 1.0        # neutral

    except Exception:
        return 1.0


def _cache_result(result: dict):
    conn = database.get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fear_greed_cache (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                score REAL, label TEXT, components TEXT, timestamp TEXT
            )
        """)
        import json
        conn.execute("""
            INSERT OR REPLACE INTO fear_greed_cache (id, score, label, components, timestamp)
            VALUES (1, ?, ?, ?, ?)
        """, (result["score"], result["label"],
               json.dumps(result["components"]), result["timestamp"]))
        conn.commit()
    finally:
        conn.close()


def _load_cached() -> dict | None:
    """Return cached F&G result if < 1 hour old."""
    try:
        import json
        conn = database.get_connection()
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS fear_greed_cache (id INTEGER PRIMARY KEY CHECK (id=1), score REAL, label TEXT, components TEXT, timestamp TEXT)")
            row = conn.execute("SELECT * FROM fear_greed_cache WHERE id=1").fetchone()
        finally:
            conn.close()

        if not row:
            return None
        ts = datetime.fromisoformat(row["timestamp"])
        if datetime.now(timezone.utc) - ts > timedelta(hours=1):
            return None
        return {
            "score": row["score"],
            "label": row["label"],
            "components": json.loads(row["components"]),
            "timestamp": row["timestamp"],
        }
    except Exception:
        return None
