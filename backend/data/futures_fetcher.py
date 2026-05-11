"""
Fetch real-time commodity/futures prices via yfinance.
Instruments: Energy, Metals, Agriculture, Bonds, FX, Indices, Crypto.
Signal weights are sourced from brain.get_weights() (self-learning).
Falls back to config.py defaults on first run / brain cold-start.
Cache: 8 seconds.
"""

import logging
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yfinance as yf

from config import (
    FUTURES_MOMENTUM_WEIGHT,
    FUTURES_EMA_WEIGHT,
    FUTURES_RSI_WEIGHT,
    FUTURES_BBANDS_WEIGHT,
    FUTURES_CONSISTENCY_WEIGHT,
)

logger = logging.getLogger(__name__)

FUTURES_INSTRUMENTS = {
    # ── Energy ──────────────────────────────────────────────────────────
    "CL=F":    {"name": "Crude Oil (WTI)",      "category": "Energy",      "unit": "$/bbl"},
    "BZ=F":    {"name": "Brent Crude Oil",      "category": "Energy",      "unit": "$/bbl"},
    "NG=F":    {"name": "Natural Gas",          "category": "Energy",      "unit": "$/MMBtu"},
    "RB=F":    {"name": "RBOB Gasoline",        "category": "Energy",      "unit": "$/gal"},
    "HO=F":    {"name": "Heating Oil",          "category": "Energy",      "unit": "$/gal"},
    # ── Metals ──────────────────────────────────────────────────────────
    "GC=F":    {"name": "Gold",                 "category": "Metals",      "unit": "$/oz"},
    "SI=F":    {"name": "Silver",               "category": "Metals",      "unit": "$/oz"},
    "HG=F":    {"name": "Copper",               "category": "Metals",      "unit": "$/lb"},
    "PL=F":    {"name": "Platinum",             "category": "Metals",      "unit": "$/oz"},
    "PA=F":    {"name": "Palladium",            "category": "Metals",      "unit": "$/oz"},
    # ── Agriculture ─────────────────────────────────────────────────────
    "ZC=F":    {"name": "Corn",                 "category": "Agriculture", "unit": "¢/bu"},
    "ZW=F":    {"name": "Wheat (CBOT)",         "category": "Agriculture", "unit": "¢/bu"},
    "KE=F":    {"name": "Wheat (KC HRW)",       "category": "Agriculture", "unit": "¢/bu"},
    "ZS=F":    {"name": "Soybeans",             "category": "Agriculture", "unit": "¢/bu"},
    "ZO=F":    {"name": "Oats",                 "category": "Agriculture", "unit": "¢/bu"},
    "SB=F":    {"name": "Sugar #11",            "category": "Agriculture", "unit": "¢/lb"},
    "KC=F":    {"name": "Coffee",               "category": "Agriculture", "unit": "¢/lb"},
    "CT=F":    {"name": "Cotton",               "category": "Agriculture", "unit": "¢/lb"},
    "CC=F":    {"name": "Cocoa",                "category": "Agriculture", "unit": "$/t"},
    # ── Indices ─────────────────────────────────────────────────────────
    "ES=F":    {"name": "S&P 500 Futures",      "category": "Indices",     "unit": "pts"},
    "NQ=F":    {"name": "NASDAQ 100 Futures",   "category": "Indices",     "unit": "pts"},
    "YM=F":    {"name": "Dow Jones Futures",    "category": "Indices",     "unit": "pts"},
    "RTY=F":   {"name": "Russell 2000 Futures", "category": "Indices",     "unit": "pts"},
    "NKD=F":   {"name": "Nikkei 225 Futures",   "category": "Indices",     "unit": "pts"},
    "GD=F":    {"name": "S&P/TSX 60 Futures",   "category": "Indices",     "unit": "pts"},
    # ── Bonds / Rates ────────────────────────────────────────────────────
    "ZB=F":    {"name": "30Y T-Bond",           "category": "Bonds",       "unit": "pts"},
    "ZN=F":    {"name": "10Y T-Note",           "category": "Bonds",       "unit": "pts"},
    "ZF=F":    {"name": "5Y T-Note",            "category": "Bonds",       "unit": "pts"},
    "ZT=F":    {"name": "2Y T-Note",            "category": "Bonds",       "unit": "pts"},
    # ── FX ──────────────────────────────────────────────────────────────
    "EURUSD=X": {"name": "EUR/USD",             "category": "FX",          "unit": "rate"},
    "GBPUSD=X": {"name": "GBP/USD",             "category": "FX",          "unit": "rate"},
    "USDJPY=X": {"name": "USD/JPY",             "category": "FX",          "unit": "rate"},
    "AUDUSD=X": {"name": "AUD/USD",             "category": "FX",          "unit": "rate"},
    "USDCAD=X": {"name": "USD/CAD",             "category": "FX",          "unit": "rate"},
    "USDCHF=X": {"name": "USD/CHF",             "category": "FX",          "unit": "rate"},
    "USDINR=X": {"name": "USD/INR",             "category": "FX",          "unit": "rate"},
    # ── Crypto ──────────────────────────────────────────────────────────
    "BTC-USD":  {"name": "Bitcoin",             "category": "Crypto",      "unit": "USD"},
    "ETH-USD":  {"name": "Ethereum",            "category": "Crypto",      "unit": "USD"},
    "BNB-USD":  {"name": "BNB",                 "category": "Crypto",      "unit": "USD"},
    "SOL-USD":  {"name": "Solana",              "category": "Crypto",      "unit": "USD"},
    "XRP-USD":  {"name": "XRP",                 "category": "Crypto",      "unit": "USD"},
    "ADA-USD":  {"name": "Cardano",             "category": "Crypto",      "unit": "USD"},
}

_quote_cache: dict = {}
_cache_ts: float = 0.0
CACHE_TTL = 8  # seconds


def _get_weights() -> dict:
    """Load live weights from brain (self-learning). Falls back to config defaults."""
    try:
        from trading.brain import get_weights
        return get_weights()
    except Exception:
        return {
            "momentum":    FUTURES_MOMENTUM_WEIGHT,
            "ema":         FUTURES_EMA_WEIGHT,
            "rsi":         FUTURES_RSI_WEIGHT,
            "bbands":      FUTURES_BBANDS_WEIGHT,
            "consistency": FUTURES_CONSISTENCY_WEIGHT,
        }


def _compute_signal(current: float, prev: float, hist: list) -> dict:
    """
    Weighted signal engine — weights from brain.get_weights() (self-learning).
    Falls back to config.py on first run.
    Returns component raw scores so brain can learn from each trade.
    Final score in [-1, +1]. >0 = LONG, <0 = SHORT.
    """
    if prev <= 0 or current <= 0 or len(hist) < 5:
        return {"signal": "NEUTRAL", "confidence": 0.0, "reason": "—", "components": {}}

    w = _get_weights()
    arr = np.array(hist, dtype=float)
    pct = (current - prev) / prev
    reasons = []

    # ── Momentum ──────────────────────────────────────────────────────
    mom_raw = float(np.tanh(pct / 0.01))   # 1% move → 0.76, 2% → 0.96
    mom_score = mom_raw * w["momentum"]
    reasons.append(f"Δ{pct:+.2%}")

    # ── EMA crossover ─────────────────────────────────────────────────
    ema_raw = 0.0
    if len(arr) >= 20:
        s = pd.Series(arr[-30:])
        ema5  = float(s.ewm(span=5).mean().iloc[-1])
        ema20 = float(s.ewm(span=20).mean().iloc[-1])
        sep = (ema5 - ema20) / (ema20 + 1e-9)
        ema_raw = float(np.tanh(sep / 0.005))
        reasons.append(f"EMA{'↑' if ema5 > ema20 else '↓'}")
    elif len(arr) >= 10:
        s = pd.Series(arr)
        ema5  = float(s.ewm(span=5).mean().iloc[-1])
        ema10 = float(s.ewm(span=10).mean().iloc[-1])
        sep   = (ema5 - ema10) / (ema10 + 1e-9)
        ema_raw = float(np.tanh(sep / 0.005))
    ema_score = ema_raw * w["ema"]

    # ── RSI ───────────────────────────────────────────────────────────
    rsi_raw = 0.0
    rsi = 50.0
    if len(arr) >= 14:
        deltas = np.diff(arr[-15:])
        gains  = deltas.clip(min=0).mean()
        losses = (-deltas).clip(min=0).mean()
        rsi = 100 - 100 / (1 + gains / (losses + 1e-9))
        rsi_raw = float(np.tanh((50 - rsi) / 20))
        reasons.append(f"RSI={rsi:.0f}")
    rsi_score = rsi_raw * w["rsi"]

    # ── Bollinger Band position ────────────────────────────────────────
    bb_raw = 0.0
    if len(arr) >= 20:
        window = arr[-20:]
        bb_mid = window.mean()
        bb_std = window.std()
        if bb_std > 0:
            z = (current - bb_mid) / bb_std
            bb_raw = float(np.tanh(-z / 2))
            reasons.append(f"BB{'↑' if z > 1 else '↓' if z < -1 else '~'}{z:+.1f}σ")
    bb_score = bb_raw * w["bbands"]

    # ── Triple-EMA consistency ────────────────────────────────────────
    cons_raw = 0.0
    if len(arr) >= 20:
        s = pd.Series(arr[-30:])
        e3  = float(s.ewm(span=3).mean().iloc[-1])
        e8  = float(s.ewm(span=8).mean().iloc[-1])
        e21 = float(s.ewm(span=21).mean().iloc[-1])
        if e3 > e8 > e21:
            cons_raw = 1.0
        elif e3 < e8 < e21:
            cons_raw = -1.0
        reasons.append(f"{'↑↑↑' if cons_raw > 0 else '↓↓↓' if cons_raw < 0 else '~~~'}")
    consistency = cons_raw * w["consistency"]

    # ── Composite ─────────────────────────────────────────────────────
    score = float(np.clip(mom_score + ema_score + rsi_score + bb_score + consistency, -0.95, 0.95))

    if score > 0.08:
        signal = "LONG"
        conf   = round(abs(score), 3)
    elif score < -0.08:
        signal = "SHORT"
        conf   = round(abs(score), 3)
    else:
        signal = "NEUTRAL"
        conf   = 0.0

    return {
        "signal":     signal,
        "confidence": min(conf, 0.95),
        "reason":     " ".join(reasons),
        "components": {
            "momentum":    round(mom_raw, 4),
            "ema":         round(ema_raw, 4),
            "rsi":         round(rsi_raw, 4),
            "bbands":      round(bb_raw, 4),
            "consistency": round(cons_raw, 4),
        },
    }


def fetch_quotes() -> list[dict]:
    """Fetch all instruments. Returns cached data if within TTL."""
    global _quote_cache, _cache_ts

    if _quote_cache and (time.time() - _cache_ts) < CACHE_TTL:
        return list(_quote_cache.values())

    symbols = list(FUTURES_INSTRUMENTS.keys())
    new_quotes: dict = {}

    try:
        raw = yf.download(
            symbols,
            period="5d",
            interval="1h",
            group_by="ticker",
            auto_adjust=True,
            progress=False,
            threads=True,
        )

        multi = hasattr(raw.columns, "levels") and len(raw.columns.levels) > 1

        for sym in symbols:
            meta = FUTURES_INSTRUMENTS[sym]
            try:
                df = raw[sym] if multi else raw
                df = df.dropna(subset=["Close"])
                if len(df) < 2:
                    continue

                cur    = float(df["Close"].iloc[-1])
                prev   = float(df["Close"].iloc[-2])
                d_open = float(df["Open"].iloc[0])
                d_high = float(df["High"].max())
                d_low  = float(df["Low"].min())
                vol    = float(df["Volume"].iloc[-1]) if "Volume" in df.columns else 0
                hist   = df["Close"].tolist()

                sig = _compute_signal(cur, prev, hist)
                change_pct = (cur - d_open) / d_open * 100 if d_open else 0

                new_quotes[sym] = {
                    "symbol":        sym,
                    "name":          meta["name"],
                    "category":      meta["category"],
                    "unit":          meta["unit"],
                    "price":         round(cur, 4),
                    "prev_close":    round(prev, 4),
                    "day_open":      round(d_open, 4),
                    "day_high":      round(d_high, 4),
                    "day_low":       round(d_low, 4),
                    "volume":        int(vol),
                    "change_pct":    round(change_pct, 3),
                    "change_abs":    round(cur - d_open, 4),
                    "signal":        sig["signal"],
                    "confidence":    sig["confidence"],
                    "signal_reason": sig["reason"],
                    "components":    sig.get("components", {}),
                    "updated_at":    datetime.now(timezone.utc).isoformat(),
                }
            except Exception as exc:
                logger.debug("Skip %s: %s", sym, exc)

    except Exception as exc:
        logger.warning("Batch futures fetch error: %s", exc)
        if _quote_cache:
            return list(_quote_cache.values())

    if new_quotes:
        _quote_cache = new_quotes
        _cache_ts = time.time()

    return list(_quote_cache.values())


def get_chart(symbol: str, period: str = "5d", interval: str = "15m") -> list[dict]:
    """Fetch OHLCV candles for chart display."""
    try:
        df = yf.download(symbol, period=period, interval=interval,
                         auto_adjust=True, progress=False)
        df = df.dropna(subset=["Close"])
        candles = []
        for idx, row in df.iterrows():
            candles.append({
                "t": str(idx),
                "o": round(float(row["Open"]), 4),
                "h": round(float(row["High"]), 4),
                "l": round(float(row["Low"]), 4),
                "c": round(float(row["Close"]), 4),
                "v": int(row["Volume"]) if not pd.isna(row.get("Volume", 0)) else 0,
            })
        return candles[-200:]
    except Exception as exc:
        logger.warning("Chart fetch failed for %s: %s", symbol, exc)
        return []
