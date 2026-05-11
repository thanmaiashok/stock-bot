"""
Pattern detection engine: VCP, NR7/Inside Day, Weinstein Stage Analysis, BB Squeeze.

VCP + Stage Analysis adapted from xang1234/stock-screener (Apache 2.0)
  Source: https://github.com/xang1234/stock-screener
  Copyright 2024 xang1234. Licensed under Apache License 2.0.

BB crossover logic adapted from kumarAnand05/Stock-Trading-Screener (MIT)
  Source: https://github.com/kumarAnand05/Stock-Trading-Screener

All adaptations: removed framework dependencies, wired to our SQLite price_history table.
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

import database

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data loader
# ---------------------------------------------------------------------------

def _load_prices(ticker: str, limit: int = 200) -> pd.DataFrame:
    conn = database.get_connection()
    try:
        rows = conn.execute(
            """SELECT date, open, high, low, close, volume
               FROM price_history
               WHERE ticker=? AND interval='1d' AND close IS NOT NULL
               ORDER BY date ASC LIMIT ?""",
            (ticker, limit),
        ).fetchall()
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame([dict(r) for r in rows])
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        return df.dropna(subset=["close"])
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# VCP — Volatility Contraction Pattern
# Adapted from xang1234/stock-screener legacy_vcp_detection.py (Apache 2.0)
# ---------------------------------------------------------------------------

def _find_peaks(prices: np.ndarray, order: int = 4) -> list[int]:
    peaks = []
    for i in range(order, len(prices) - order):
        if prices[i] > np.max(prices[i - order:i]) and prices[i] > np.max(prices[i + 1:i + order + 1]):
            peaks.append(i)
    return peaks


def _vcp_bases(prices_recent_first: pd.Series, min_duration: int = 10) -> list[dict]:
    """Find consolidation bases (pullbacks from local highs)."""
    arr = prices_recent_first.values
    peaks = _find_peaks(arr)
    if len(peaks) < 2:
        return []

    bases = []
    for i in range(len(peaks) - 1):
        pi, ni = peaks[i], peaks[i + 1]
        seg = arr[pi:ni + 1]
        if len(seg) < min_duration:
            continue
        high = arr[pi]
        low = seg.min()
        if high <= 0:
            continue
        depth = (high - low) / high * 100
        is_first = len(bases) == 0
        valid = (5 <= depth <= 45) if is_first else (5 <= depth <= 35)
        if valid:
            bases.append({"start_idx": pi, "end_idx": ni, "high": high, "low": low, "depth_pct": depth})

    return bases[:5]


def detect_vcp(df: pd.DataFrame) -> dict:
    """
    Detect Volatility Contraction Pattern (Minervini methodology).
    Returns detected bool, score 0-100, pivot info.
    """
    if df.empty or len(df) < 60:
        return {"detected": False, "score": 0, "reason": "insufficient_data"}

    # Most-recent-first for VCP logic
    closes = df["close"].iloc[::-1].reset_index(drop=True)
    volumes = df["volume"].iloc[::-1].reset_index(drop=True) if "volume" in df.columns else None

    lookback = min(150, len(closes))
    prices = closes.iloc[:lookback]
    bases = _vcp_bases(prices)

    if len(bases) < 3:
        return {"detected": False, "score": 0, "num_bases": len(bases), "reason": "too_few_bases"}

    # Contraction check: depths should decrease (oldest → newest = reversed)
    depths = [b["depth_pct"] for b in reversed(bases)]
    pairs = len(depths) - 1
    decreasing = sum(1 for i in range(pairs) if depths[i] > depths[i + 1])
    contraction_ratio = decreasing / pairs if pairs > 0 else 0
    contracting = contraction_ratio >= 0.75

    if contraction_ratio == 1.0:
        depth_score = 100
    elif contraction_ratio >= 0.75:
        depth_score = 80
    else:
        depth_score = contraction_ratio * 50

    # Volume contraction
    vol_score = 0.0
    contracting_volume = False
    if volumes is not None:
        base_vols = []
        for b in bases:
            seg = volumes.iloc[b["end_idx"]:b["start_idx"] + 1]
            if len(seg) > 0:
                base_vols.append(float(seg.mean()))
        if len(base_vols) >= 3:
            contracting_volume = all(base_vols[i] > base_vols[i + 1] for i in range(len(base_vols) - 1))
            if contracting_volume:
                ratios = [base_vols[i + 1] / base_vols[i] for i in range(len(base_vols) - 1) if base_vols[i] > 0]
                avg = np.mean(ratios) if ratios else 1.0
                vol_score = 100 if 0.5 <= avg <= 0.8 else (70 if 0.4 <= avg <= 0.9 else 50)

    # Tightness near highs
    current = float(prices.iloc[0])
    recent_high = max(b["high"] for b in bases)
    dist_pct = (recent_high - current) / recent_high * 100 if recent_high > 0 else 999
    tight = dist_pct <= 5
    tightness_score = 100 if dist_pct <= 2 else (80 if dist_pct <= 5 else (50 if dist_pct <= 10 else 0))

    # ATR contraction
    changes = prices.diff().abs()
    atr = changes.rolling(14, min_periods=14).mean().dropna()
    atr_score = 0.0
    if len(atr) >= 40:
        recent_atr = float(atr.iloc[:10].mean())
        past_atr = float(atr.iloc[30:40].mean())
        if past_atr > 0:
            ratio = recent_atr / past_atr
            atr_score = 100 if ratio <= 0.5 else (80 if ratio <= 0.7 else (60 if ratio <= 0.85 else (40 if ratio <= 1.0 else 0)))

    score = depth_score * 0.35 + vol_score * 0.25 + tightness_score * 0.25 + atr_score * 0.15

    # Pivot
    pivot = max(b["high"] for b in bases[:2]) if len(bases) >= 2 else bases[0]["high"]
    dist_to_pivot = (pivot - current) / current * 100 if current > 0 else None
    ready_breakout = dist_to_pivot is not None and dist_to_pivot <= 3

    return {
        "detected": bool(score >= 65 and contracting and tight),
        "score": round(score, 1),
        "num_bases": len(bases),
        "contracting_depth": contracting,
        "contraction_ratio": round(contraction_ratio, 2),
        "contracting_volume": contracting_volume,
        "bases_depths": [round(b["depth_pct"], 1) for b in bases],
        "pivot": round(pivot, 2),
        "distance_to_pivot_pct": round(dist_to_pivot, 2) if dist_to_pivot is not None else None,
        "ready_for_breakout": ready_breakout,
        "current_price": round(current, 2),
        "recent_high": round(recent_high, 2),
    }


# ---------------------------------------------------------------------------
# NR7 / Inside Day
# Adapted from xang1234/stock-screener nr7_inside_day.py (Apache 2.0)
# ---------------------------------------------------------------------------

def detect_nr7_inside_day(df: pd.DataFrame) -> dict:
    """
    Detect NR7 (Narrowest Range in 7 days) and/or Inside Day patterns.
    Both signal coiled-spring setups before potential breakout.
    """
    if df.empty or len(df) < 30:
        return {"detected": False, "score": 0, "reason": "insufficient_data"}

    if "high" not in df.columns or "low" not in df.columns:
        return {"detected": False, "score": 0, "reason": "no_high_low_data"}

    high = df["high"].values
    low = df["low"].values
    close = df["close"].values
    volume = df["volume"].values if "volume" in df.columns else None

    daily_ranges = high - low
    ema21 = pd.Series(close).ewm(span=21, adjust=False).mean().values
    vol_mean20 = None
    if volume is not None:
        vol_mean20 = pd.Series(volume).rolling(20, min_periods=5).mean().values

    signals = []
    for i in range(7, len(df) - 1):
        # NR7: today's range is smallest of last 7 days
        window_ranges = daily_ranges[i - 6:i + 1]
        is_nr7 = bool(daily_ranges[i] == window_ranges.min())

        # Inside Day: today's range completely within yesterday's range
        is_inside = bool(high[i] <= high[i - 1] and low[i] >= low[i - 1])

        if not (is_nr7 or is_inside):
            continue

        subtype = "nr7_inside_day" if (is_nr7 and is_inside) else ("nr7" if is_nr7 else "inside_day")
        range_pct = (daily_ranges[i] / close[i] * 100) if close[i] > 0 else 0
        vol_ratio = (volume[i] / vol_mean20[i] if (volume is not None and vol_mean20 is not None and vol_mean20[i] > 0) else 1.0)
        close_above_ema = close[i] > ema21[i]
        recency = len(df) - 1 - i

        # Score (0-1)
        subtype_bonus = {"nr7_inside_day": 0.18, "nr7": 0.10, "inside_day": 0.08}.get(subtype, 0.05)
        tightness = max(0.0, 1.0 - range_pct / 4.0)
        vol_dry = max(0.0, 1.0 - min(max(vol_ratio, 0.0), 2.0))
        recency_c = max(0.0, 1.0 - recency / 20)
        sig_score = 0.20 + subtype_bonus + tightness * 0.28 + vol_dry * 0.12 + (0.08 if close_above_ema else 0) + recency_c * 0.14

        signals.append({
            "idx": i, "subtype": subtype, "is_nr7": is_nr7, "is_inside": is_inside,
            "score": sig_score, "recency_bars": recency,
            "trigger_high": round(float(high[i]), 4), "trigger_low": round(float(low[i]), 4),
            "range_pct": round(range_pct, 4), "vol_ratio": round(float(vol_ratio), 3),
            "close_above_ema21": bool(close_above_ema),
        })

    if not signals:
        return {"detected": False, "score": 0, "reason": "no_nr7_inside_day"}

    signals.sort(key=lambda s: (-s["score"], s["recency_bars"]))
    best = signals[0]
    score = min(100.0, max(0.0, best["score"] * 100))

    return {
        "detected": True,
        "score": round(score, 1),
        "subtype": best["subtype"],
        "is_nr7": best["is_nr7"],
        "is_inside_day": best["is_inside"],
        "trigger_high": best["trigger_high"],
        "trigger_low": best["trigger_low"],
        "range_pct": best["range_pct"],
        "volume_ratio": best["vol_ratio"],
        "close_above_ema21": best["close_above_ema21"],
        "recency_bars": best["recency_bars"],
    }


# ---------------------------------------------------------------------------
# Weinstein Stage Analysis
# Adapted from xang1234/stock-screener stage_analysis.py (Apache 2.0)
# ---------------------------------------------------------------------------

def detect_stage(df: pd.DataFrame) -> dict:
    """
    Classify stock into Weinstein Stage 1/2/3/4.
    Stage 2 = uptrend, ideal buy zone.
    """
    if df.empty or len(df) < 50:
        return {"stage": 0, "stage_name": "Unknown", "confidence": 0, "reason": "insufficient_data"}

    close = df["close"]
    current = float(close.iloc[-1])

    # Moving averages
    ma50 = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
    ma150 = float(close.ewm(span=150, adjust=False).mean().iloc[-1]) if len(close) >= 50 else ma50
    ma200_series = close.rolling(200, min_periods=30).mean().dropna()

    if len(ma200_series) < 25:
        return {"stage": 0, "stage_name": "Unknown", "confidence": 0, "reason": "need_more_history"}

    ma200 = float(ma200_series.iloc[-1])
    ma200_month_ago = float(ma200_series.iloc[-22]) if len(ma200_series) >= 22 else float(ma200_series.iloc[0])

    above_200 = current > ma200
    ma_change_pct = (ma200 - ma200_month_ago) / ma200_month_ago * 100 if ma200_month_ago > 0 else 0
    ma_rising = ma_change_pct > 1.0
    ma_falling = ma_change_pct < -1.0
    ma_flat = not ma_rising and not ma_falling

    # Price trend via linear regression (last 60 bars)
    n = min(60, len(close))
    y = close.values[-n:]
    x = np.arange(n)
    try:
        slope, _ = np.polyfit(x, y, 1)
        norm_slope = (slope / np.mean(y)) * 100
        price_trend = "uptrend" if norm_slope > 0.05 else ("downtrend" if norm_slope < -0.05 else "sideways")
    except Exception:
        price_trend = "sideways"

    # Stage classification (Weinstein/Minervini)
    if current > ma50 > ma150 > ma200 and ma_rising:
        stage = 2
    elif above_200 and ma_flat:
        stage = 3
    elif above_200 and ma_rising and price_trend == "uptrend":
        stage = 2
    elif above_200 and (not ma_rising or ma50 < ma200):
        stage = 3
    elif not above_200 and ma_falling and price_trend == "downtrend":
        stage = 4
    elif not above_200 and ma_flat:
        stage = 1
    elif not above_200 and ma_rising:
        stage = 1
    elif not above_200:
        stage = 4
    else:
        stage = 3

    # Confidence
    conf = 50
    if stage == 2:
        if above_200: conf += 12
        if ma_rising: conf += 12
        if price_trend == "uptrend": conf += 12
    elif stage == 4:
        if not above_200: conf += 12
        if ma_falling: conf += 12
        if price_trend == "downtrend": conf += 12
    elif stage == 1:
        if ma_flat: conf += 15
    elif stage == 3:
        if not ma_rising: conf += 10

    stage_names = {1: "Basing", 2: "Advancing", 3: "Topping", 4: "Declining", 0: "Unknown"}
    stage_desc = {
        1: "Consolidating around flattening MA. Watch for Stage 2 breakout.",
        2: "Uptrend above rising 200MA — ideal buy zone (Weinstein/Minervini).",
        3: "Topping / distribution. Consider reducing positions.",
        4: "Downtrend below falling 200MA. Avoid.",
    }

    return {
        "stage": stage,
        "stage_name": stage_names.get(stage, "Unknown"),
        "description": stage_desc.get(stage, ""),
        "confidence": min(100, conf),
        "above_ma200": above_200,
        "ma200_trend": "rising" if ma_rising else ("falling" if ma_falling else "flat"),
        "price_trend": price_trend,
        "ma50": round(ma50, 2),
        "ma200": round(ma200, 2),
        "current": round(current, 2),
    }


# ---------------------------------------------------------------------------
# Bollinger Band Squeeze
# Inspired by kumarAnand05/Stock-Trading-Screener (MIT)
# ---------------------------------------------------------------------------

def detect_bb_squeeze(df: pd.DataFrame) -> dict:
    """
    Detect Bollinger Band squeeze: bands narrowing = coiled volatility.
    BB width at multi-period low = potential explosive move coming.
    """
    if df.empty or len(df) < 30:
        return {"detected": False, "score": 0}

    close = df["close"]
    sma20 = close.rolling(20, min_periods=10).mean()
    std20 = close.rolling(20, min_periods=10).std()
    bb_width = (4 * std20 / sma20 * 100).dropna()

    if len(bb_width) < 20:
        return {"detected": False, "score": 0}

    current_width = float(bb_width.iloc[-1])
    min_width_50 = float(bb_width.tail(50).min())
    pct_above_min = (current_width - min_width_50) / min_width_50 * 100 if min_width_50 > 0 else 999

    # Price position relative to bands
    current = float(close.iloc[-1])
    upper = float(sma20.iloc[-1] + 2 * std20.iloc[-1])
    lower = float(sma20.iloc[-1] - 2 * std20.iloc[-1])
    pband = (current - lower) / (upper - lower) if (upper - lower) > 0 else 0.5

    squeezed = pct_above_min <= 10
    score = max(0, 100 - pct_above_min * 5) if squeezed else max(0, 50 - pct_above_min * 2)

    return {
        "detected": squeezed,
        "score": round(score, 1),
        "bb_width": round(current_width, 2),
        "bb_width_min_50d": round(min_width_50, 2),
        "pct_above_min": round(pct_above_min, 1),
        "price_band_position": round(pband, 3),
    }


# ---------------------------------------------------------------------------
# Main scan function
# ---------------------------------------------------------------------------

def scan_patterns(ticker: str) -> dict:
    """
    Run all pattern detectors for a ticker.
    Returns dict with vcp, nr7, stage, bb_squeeze, and composite pattern_score (0-1).
    """
    df = _load_prices(ticker, limit=250)
    if df.empty or len(df) < 20:
        return {
            "ticker": ticker,
            "pattern_score": 0.0,
            "vcp": {"detected": False, "score": 0},
            "nr7": {"detected": False, "score": 0},
            "stage": {"stage": 0, "stage_name": "Unknown", "confidence": 0},
            "bb_squeeze": {"detected": False, "score": 0},
            "patterns": [],
        }

    vcp = detect_vcp(df)
    nr7 = detect_nr7_inside_day(df)
    stage = detect_stage(df)
    bb = detect_bb_squeeze(df)

    # Composite pattern score (0-1)
    # VCP strongest signal (40%), Stage 2 filter (30%), NR7 trigger (20%), BB squeeze (10%)
    vcp_c = vcp["score"] / 100 * 0.40
    stage_c = (stage["confidence"] / 100 * (1.0 if stage["stage"] == 2 else 0.3 if stage["stage"] == 1 else 0.1)) * 0.30
    nr7_c = nr7["score"] / 100 * 0.20
    bb_c = bb["score"] / 100 * 0.10
    pattern_score = round(min(1.0, vcp_c + stage_c + nr7_c + bb_c), 4)

    active_patterns = []
    if vcp["detected"]:
        active_patterns.append("VCP")
    if nr7["detected"]:
        active_patterns.append(nr7.get("subtype", "NR7").upper())
    if bb["detected"]:
        active_patterns.append("BB_SQUEEZE")
    if stage["stage"] == 2:
        active_patterns.append("STAGE2")

    return {
        "ticker": ticker,
        "pattern_score": pattern_score,
        "patterns": active_patterns,
        "vcp": vcp,
        "nr7": nr7,
        "stage": stage,
        "bb_squeeze": bb,
    }
