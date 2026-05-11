"""
Market Breadth Engine — computed from local price_history DB. Zero external deps.

Indicators (all formulas from public domain / academic finance literature):

  McClellan Oscillator — Marian & Sherman McClellan (1969), public domain formula.
    Advance-Decline Net = advancing - declining issues daily
    McClellan = EMA19(net) - EMA39(net)
    Above zero = expanding breadth (bullish), below = contracting (bearish).

  Advance-Decline Line (Cumulative A/D) — oldest breadth indicator, ~1926.
    Cumulative sum of (advances - declines). Divergence from price = early warning.

  New High / New Low Ratio — % of universe hitting 52-week highs vs lows.
    NH-NL > 0 = majority hitting highs (bullish), < 0 = lows dominate.

  TRIN (Arms Index) — Richard Arms (1967), public domain.
    TRIN = (Advances/Declines) / (Advance_Volume / Decline_Volume)
    < 1 = bullish (more volume in advances), > 1 = bearish, > 2 = panic selling.

  Percent Above 50/200 MA — % of universe above their moving averages.
    >70% above 200MA = healthy bull, <30% = bear market.

All computed from our SQLite price_history without any API calls.
"""

import logging
from datetime import datetime, timezone, timedelta

import numpy as np

import database

logger = logging.getLogger(__name__)


def _get_latest_date() -> str:
    conn = database.get_connection()
    try:
        row = conn.execute(
            "SELECT MAX(date) as d FROM price_history WHERE interval='1d'"
        ).fetchone()
        return row["d"] if row else ""
    finally:
        conn.close()


def _daily_advance_decline(days: int = 90) -> list[dict]:
    """
    For each trading day compute: advances, declines, unchanged, advance_vol, decline_vol.
    Returns list sorted ASC by date.
    """
    conn = database.get_connection()
    try:
        # Get all daily closes + volumes with previous day close
        rows = conn.execute("""
            SELECT p.date, p.ticker, p.close, p.volume,
                   LAG(p.close) OVER (PARTITION BY p.ticker ORDER BY p.date) as prev_close
            FROM price_history p
            JOIN ticker_universe u ON p.ticker = u.ticker
            WHERE p.interval='1d'
              AND u.active=1
              AND p.date >= date('now', ?)
            ORDER BY p.date ASC
        """, (f"-{days} days",)).fetchall()
    finally:
        conn.close()

    if not rows:
        return []

    # Group by date
    by_date: dict[str, dict] = {}
    for row in rows:
        date = row["date"]
        close = row["close"]
        prev = row["prev_close"]
        vol = row["volume"] or 0
        if prev is None or prev <= 0 or close is None:
            continue
        if date not in by_date:
            by_date[date] = {"advances": 0, "declines": 0, "unchanged": 0,
                             "adv_vol": 0, "dec_vol": 0}
        change = close - prev
        if change > 0:
            by_date[date]["advances"] += 1
            by_date[date]["adv_vol"] += vol
        elif change < 0:
            by_date[date]["declines"] += 1
            by_date[date]["dec_vol"] += vol
        else:
            by_date[date]["unchanged"] += 1

    return [{"date": d, **v} for d, v in sorted(by_date.items())]


def _ema(values: list[float], span: int) -> list[float]:
    """Exponential moving average."""
    k = 2 / (span + 1)
    result = [values[0]]
    for v in values[1:]:
        result.append(v * k + result[-1] * (1 - k))
    return result


def compute_breadth(days: int = 90) -> dict:
    """
    Compute all market breadth indicators for last N days.
    Returns dict with McClellan, A/D line, TRIN, NH/NL, MA breadth.
    """
    ad_data = _daily_advance_decline(days + 40)  # extra for EMA warm-up
    if len(ad_data) < 5:
        return {"error": "Insufficient price history for breadth computation"}

    # ── McClellan Oscillator ──────────────────────────────────────────────
    nets = [d["advances"] - d["declines"] for d in ad_data]
    ema19 = _ema(nets, 19)
    ema39 = _ema(nets, 39)
    mcclellan = [round(e19 - e39, 2) for e19, e39 in zip(ema19, ema39)]

    # ── Cumulative Advance-Decline Line ───────────────────────────────────
    ad_line = []
    cumulative = 0
    for d in ad_data:
        cumulative += d["advances"] - d["declines"]
        ad_line.append(cumulative)

    # ── TRIN (Arms Index) ─────────────────────────────────────────────────
    trin_series = []
    for d in ad_data:
        adv = d["advances"] or 1
        dec = d["declines"] or 1
        adv_vol = d["adv_vol"] or 1
        dec_vol = d["dec_vol"] or 1
        trin = (adv / dec) / (adv_vol / dec_vol)
        trin_series.append(round(trin, 3))

    # Take last `days` worth of data
    cutoff = -days
    dates = [d["date"] for d in ad_data][cutoff:]
    advances = [d["advances"] for d in ad_data][cutoff:]
    declines = [d["declines"] for d in ad_data][cutoff:]
    mcclellan_out = mcclellan[cutoff:]
    ad_line_out = ad_line[cutoff:]
    trin_out = trin_series[cutoff:]

    # ── New High / New Low Ratio ──────────────────────────────────────────
    nh_nl = _new_high_low_ratio()

    # ── Percent Above MA ──────────────────────────────────────────────────
    pct_above = _pct_above_ma()

    # ── Summary signals ──────────────────────────────────────────────────
    latest_mcc = mcclellan_out[-1] if mcclellan_out else 0
    latest_trin = trin_out[-1] if trin_out else 1.0
    latest_adv = advances[-1] if advances else 0
    latest_dec = declines[-1] if declines else 0

    breadth_score = _breadth_score(latest_mcc, latest_trin, nh_nl, pct_above)

    return {
        "dates": dates,
        "advances": advances,
        "declines": declines,
        "mcclellan": mcclellan_out,
        "ad_line": ad_line_out,
        "trin": trin_out,
        "new_high_low": nh_nl,
        "pct_above_50ma": pct_above.get("pct_50ma"),
        "pct_above_200ma": pct_above.get("pct_200ma"),
        "breadth_score": breadth_score,
        "breadth_label": _breadth_label(breadth_score),
        "latest": {
            "date": dates[-1] if dates else "",
            "mcclellan": latest_mcc,
            "trin": latest_trin,
            "advances": latest_adv,
            "declines": latest_dec,
            "ad_ratio": round(latest_adv / max(latest_dec, 1), 2),
        },
        "signals": {
            "mcclellan_bullish": latest_mcc > 0,
            "trin_bullish": latest_trin < 1.0,
            "trin_panic": latest_trin > 2.0,
            "breadth_bull": breadth_score > 0.3,
            "breadth_bear": breadth_score < -0.3,
        },
    }


def _new_high_low_ratio() -> dict:
    """% of universe at 52-week highs vs lows."""
    conn = database.get_connection()
    try:
        rows = conn.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN close >= max52 * 0.98 THEN 1 ELSE 0 END) as new_highs,
                   SUM(CASE WHEN close <= min52 * 1.02 THEN 1 ELSE 0 END) as new_lows
            FROM (
                SELECT ticker,
                       MAX(close) OVER (PARTITION BY ticker ORDER BY date
                           ROWS BETWEEN 251 PRECEDING AND CURRENT ROW) as max52,
                       MIN(close) OVER (PARTITION BY ticker ORDER BY date
                           ROWS BETWEEN 251 PRECEDING AND CURRENT ROW) as min52,
                       close, date
                FROM price_history WHERE interval='1d'
            ) sub
            WHERE date = (SELECT MAX(date) FROM price_history WHERE interval='1d')
        """).fetchone()
    except Exception:
        return {}
    finally:
        conn.close()

    if not rows or not rows["total"]:
        return {}
    total = rows["total"]
    highs = rows["new_highs"] or 0
    lows = rows["new_lows"] or 0
    return {
        "new_highs": highs,
        "new_lows": lows,
        "total": total,
        "nh_pct": round(highs / total * 100, 1),
        "nl_pct": round(lows / total * 100, 1),
        "net_hl": round((highs - lows) / total * 100, 1),
    }


def _pct_above_ma() -> dict:
    """% of universe above 50-day and 200-day moving averages."""
    conn = database.get_connection()
    try:
        rows = conn.execute("""
            SELECT AVG(CASE WHEN close > ma50 THEN 100.0 ELSE 0.0 END) as pct_50ma,
                   AVG(CASE WHEN close > ma200 THEN 100.0 ELSE 0.0 END) as pct_200ma
            FROM (
                SELECT ticker, close, date,
                       AVG(close) OVER (PARTITION BY ticker ORDER BY date
                           ROWS BETWEEN 49 PRECEDING AND CURRENT ROW) as ma50,
                       AVG(close) OVER (PARTITION BY ticker ORDER BY date
                           ROWS BETWEEN 199 PRECEDING AND CURRENT ROW) as ma200
                FROM price_history WHERE interval='1d'
            ) sub
            WHERE date = (SELECT MAX(date) FROM price_history WHERE interval='1d')
        """).fetchone()
    except Exception:
        return {}
    finally:
        conn.close()

    return {
        "pct_50ma": round(rows["pct_50ma"] or 0, 1),
        "pct_200ma": round(rows["pct_200ma"] or 0, 1),
    }


def _breadth_score(mcclellan: float, trin: float, nh_nl: dict, pct_above: dict) -> float:
    """
    Composite breadth score in [-1, 1].
    Positive = broad market bullish, negative = broad market bearish.
    """
    score = 0.0
    weights = 0

    # McClellan: range typically -200 to +200
    if mcclellan != 0:
        score += max(-1.0, min(1.0, mcclellan / 100))
        weights += 1

    # TRIN: <1 bullish, >1 bearish (inverted)
    trin_score = max(-1.0, min(1.0, (1.5 - trin) / 1.0))
    score += trin_score
    weights += 1

    # NH-NL net %
    net_hl = nh_nl.get("net_hl", 0)
    score += max(-1.0, min(1.0, net_hl / 10))
    weights += 1

    # % above 200MA: >70 = bullish, <30 = bearish
    pct200 = pct_above.get("pct_200ma", 50)
    score += max(-1.0, min(1.0, (pct200 - 50) / 30))
    weights += 1

    return round(score / max(weights, 1), 4)


def _breadth_label(score: float) -> str:
    if score > 0.5:   return "Strong Breadth (Bull)"
    if score > 0.2:   return "Positive Breadth"
    if score > -0.2:  return "Neutral Breadth"
    if score > -0.5:  return "Weak Breadth"
    return "Deteriorating Breadth (Bear)"


def get_breadth_multiplier() -> float:
    """
    Market regime multiplier for signal_engine.
    Strong breadth → amplify signals 1.15x.
    Deteriorating breadth → dampen 0.80x.
    """
    try:
        result = compute_breadth(days=10)
        score = result.get("breadth_score", 0.0)
        if score > 0.5:   return 1.15
        if score > 0.2:   return 1.05
        if score < -0.5:  return 0.80
        if score < -0.2:  return 0.90
        return 1.0
    except Exception:
        return 1.0
