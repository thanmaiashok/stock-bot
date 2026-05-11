"""
Fully automatic futures trader. No user config. Always on.
Decision weights: Momentum 35% + EMA 30% + RSI 20% + Consistency 15%
(computed in futures_fetcher._compute_signal)

Hardcoded strategy:
  confidence_threshold = 0.52   (fires on medium-strong signals)
  units_per_trade      = 1.0
  max_open_positions   = 8
  SL = 2%, TP = 4%, Leverage = 10x
"""

import logging
from datetime import datetime, timezone

import numpy as np

import database
from data.futures_fetcher import fetch_quotes
from trading.futures_trader import open_position, close_position, get_portfolio

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.52
UNITS_PER_TRADE      = 1.0
MAX_POSITIONS        = 8


# ---------------------------------------------------------------------------
# Prediction (linear regression on recent hourly closes)
# ---------------------------------------------------------------------------

_pred_cache: dict = {}
_pred_ts: float = 0.0
PRED_TTL = 900  # 15 min


def predict_prices(quotes: list[dict]) -> dict[str, dict]:
    import yfinance as yf
    preds = {}
    for q in quotes:
        sym = q["symbol"]
        try:
            df = yf.download(sym, period="10d", interval="1h",
                             auto_adjust=True, progress=False)
            closes = df["Close"].dropna().values.flatten().astype(float)
            if len(closes) < 10:
                continue
            n   = len(closes)
            x   = np.arange(n, dtype=float)
            xm  = x.mean(); ym = closes.mean()
            sl  = np.sum((x - xm) * (closes - ym)) / (np.sum((x - xm) ** 2) + 1e-9)
            ic  = ym - sl * xm
            ss_res = np.sum((closes - (sl * x + ic)) ** 2)
            ss_tot = np.sum((closes - ym) ** 2)
            r2  = max(0.0, 1 - ss_res / (ss_tot + 1e-9))
            cur = float(closes[-1])
            p1h  = float(sl * (n + 1)  + ic)
            p4h  = float(sl * (n + 4)  + ic)
            p1d  = float(sl * (n + 24) + ic)
            preds[sym] = {
                "current":   round(cur,  4),
                "pred_1h":   round(p1h,  4),
                "pred_4h":   round(p4h,  4),
                "pred_1d":   round(p1d,  4),
                "change_1h": round((p1h - cur) / cur * 100, 3),
                "change_4h": round((p4h - cur) / cur * 100, 3),
                "change_1d": round((p1d - cur) / cur * 100, 3),
                "trend":     "up" if sl > 0 else "down",
                "r2":        round(r2, 3),
                "volatility": round(float(np.std(np.diff(closes) / closes[:-1])) * 100, 3),
            }
        except Exception as exc:
            logger.debug("Prediction failed for %s: %s", sym, exc)
    return preds


def get_predictions_cached(quotes: list[dict]) -> dict:
    import time
    global _pred_cache, _pred_ts
    if _pred_cache and (time.time() - _pred_ts) < PRED_TTL:
        return _pred_cache
    _pred_cache = predict_prices(quotes)
    _pred_ts = time.time()
    return _pred_cache


# ---------------------------------------------------------------------------
# Bot status (read-only, for frontend display)
# ---------------------------------------------------------------------------

def get_bot_status() -> dict:
    """Return current bot state for display — no config, always active."""
    return {
        "enabled":              True,
        "confidence_threshold": CONFIDENCE_THRESHOLD,
        "units_per_trade":      UNITS_PER_TRADE,
        "max_open_positions":   MAX_POSITIONS,
        "strategy":             "Momentum 35% + EMA 30% + RSI 20% + Consistency 15%",
        "sl_pct":               2.0,
        "tp_pct":               4.0,
        "leverage":             10,
    }


# ---------------------------------------------------------------------------
# Auto-trade loop — called every 30s by scheduler
# ---------------------------------------------------------------------------

def run_auto_trade():
    """
    1. Fetch quotes + weighted signals.
    2. For each instrument above threshold:
       - No position → open in signal direction.
       - Opposite position → close + reverse.
       - Same direction → hold.
    3. Always on. No user override.
    """
    quotes = fetch_quotes()
    if not quotes:
        return

    portfolio  = get_portfolio()
    open_map   = {pos["symbol"]: pos["direction"] for pos in portfolio.get("positions", [])}
    open_count = len(open_map)

    for q in quotes:
        sym       = q["symbol"]
        signal    = q.get("signal", "NEUTRAL")
        conf      = float(q.get("confidence", 0))

        if signal == "NEUTRAL" or conf < CONFIDENCE_THRESHOLD:
            continue

        direction    = "long" if signal == "LONG" else "short"
        existing_dir = open_map.get(sym)

        if existing_dir == direction:
            continue  # already riding this signal

        if existing_dir and existing_dir != direction:
            # Reverse: close opposite, then open new direction below
            result = close_position(sym, q["price"],
                                    f"Bot reverse: {signal} conf={conf:.2f}")
            if result["ok"]:
                logger.info("Bot reversed %s → %s (PnL=%+.2f)", sym, direction.upper(), result.get("pnl", 0))
                open_count -= 1
            else:
                continue

        if open_count >= MAX_POSITIONS:
            logger.debug("Bot: max %d positions — skip %s", MAX_POSITIONS, sym)
            continue

        pf_fresh      = get_portfolio()
        cash          = pf_fresh.get("cash", 0)
        margin_needed = q["price"] * UNITS_PER_TRADE * 0.10

        if margin_needed > cash:
            logger.debug("Bot: insufficient cash ($%.2f) for %s margin $%.2f",
                         cash, sym, margin_needed)
            continue

        result = open_position(sym, direction, UNITS_PER_TRADE, q["price"],
                              components=q.get("components", {}))
        if result["ok"]:
            logger.info("Bot OPEN %s %s conf=%.2f margin=$%.2f",
                        direction.upper(), sym, conf, result.get("margin", 0))
            open_count += 1
        else:
            logger.debug("Bot open failed %s: %s", sym, result.get("message"))
