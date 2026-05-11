"""
TopK portfolio rotation ranker.

Strategy concept inspired by Qlib (MIT): https://github.com/microsoft/qlib
Adapted: uses our SQLite signals + price data instead of Qlib's data layer.
No Qlib dependency. Pure pandas + our database.

TopK logic: score all active tickers on composite signal, hold top-K highest-conviction.
Portfolio weight optimization via PyPortfolioOpt (MIT): https://github.com/robertmartin8/PyPortfolioOpt
Efficient Frontier + CVaR minimization replace naive equal-weight allocation.

Rotate: drop tickers that fell out of top-K, add new entrants.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import numpy as np
import pandas as pd

import database
from signals.pattern_engine import scan_patterns

try:
    from pypfopt import EfficientFrontier, risk_models, expected_returns, EfficientCVaR
    from pypfopt.exceptions import OptimizationError
    _PYPFOPT = True
except ImportError:
    _PYPFOPT = False
    logger_tmp = logging.getLogger(__name__)
    logger_tmp.warning("pyportfolioopt not installed — using equal weights. Run: pip install pyportfolioopt")

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_DEFAULT_K = 10
_SCORE_WINDOW_HOURS = 48  # use signals from last 48h
_MIN_CONFIDENCE = 0.10


# ---------------------------------------------------------------------------
# PyPortfolioOpt weight optimizer
# ---------------------------------------------------------------------------

def _load_returns_matrix(tickers: list[str], lookback_days: int = 252) -> pd.DataFrame:
    """Load daily returns for tickers from DB → DataFrame (tickers as columns)."""
    conn = database.get_connection()
    try:
        frames = {}
        for ticker in tickers:
            rows = conn.execute(
                """SELECT date, close FROM price_history
                   WHERE ticker=? AND interval='1d' AND close IS NOT NULL
                   ORDER BY date DESC LIMIT ?""",
                (ticker, lookback_days + 1),
            ).fetchall()
            if len(rows) < 30:
                continue
            closes = pd.Series(
                {r["date"]: r["close"] for r in rows}
            ).sort_index()
            frames[ticker] = closes.pct_change().dropna()
        return pd.DataFrame(frames).dropna(axis=1, thresh=20)
    finally:
        conn.close()


def optimize_weights(tickers: list[str], method: str = "max_sharpe") -> dict:
    """
    Compute optimal portfolio weights using PyPortfolioOpt (MIT).
    Source: https://github.com/robertmartin8/PyPortfolioOpt

    Methods:
      - "max_sharpe": maximize Sharpe ratio (default)
      - "min_cvar":   minimize Conditional VaR at 95% confidence (tail risk)
      - "equal":      equal weight fallback

    Returns dict: {ticker: weight, ..., "_meta": {sharpe, expected_return, volatility}}
    """
    if not _PYPFOPT or len(tickers) < 2:
        n = len(tickers)
        return {t: round(1 / n, 4) for t in tickers} if n else {}

    returns_df = _load_returns_matrix(tickers)
    valid = list(returns_df.columns)
    if len(valid) < 2:
        n = len(tickers)
        return {t: round(1 / n, 4) for t in tickers}

    try:
        mu = expected_returns.mean_historical_return(returns_df, returns_data=True, frequency=252)
        S = risk_models.CovarianceShrinkage(returns_df, returns_data=True, frequency=252).ledoit_wolf()

        if method == "min_cvar":
            ef = EfficientCVaR(mu, returns_df)
            weights = ef.min_cvar(market_neutral=False)
            cleaned = ef.clean_weights()
            meta = {"method": "min_cvar_95"}
        else:
            ef = EfficientFrontier(mu, S, weight_bounds=(0, 0.40))
            weights = ef.max_sharpe(risk_free_rate=0.05)
            cleaned = ef.clean_weights()
            perf = ef.portfolio_performance(verbose=False, risk_free_rate=0.05)
            meta = {
                "method": "max_sharpe",
                "expected_annual_return": round(perf[0], 4),
                "annual_volatility": round(perf[1], 4),
                "sharpe_ratio": round(perf[2], 4),
            }

        result = {t: round(float(w), 4) for t, w in cleaned.items() if w > 0.001}
        # Fill missing tickers with 0
        for t in tickers:
            if t not in result:
                result[t] = 0.0
        result["_meta"] = meta
        return result

    except Exception as e:
        logger.warning("PyPortfolioOpt optimization failed (%s) — equal weights", e)
        n = len(tickers)
        return {t: round(1 / n, 4) for t in tickers}


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _load_recent_signals(hours: int = _SCORE_WINDOW_HOURS) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    conn = database.get_connection()
    try:
        rows = conn.execute(
            """SELECT s.ticker, s.signal, s.confidence,
                      s.gnn_score, s.xgb_score, s.sentiment_score, s.fundamental_score,
                      u.sector, u.name
               FROM signals s
               LEFT JOIN ticker_universe u ON s.ticker = u.ticker
               WHERE s.timestamp >= ?
               ORDER BY s.ticker, s.timestamp DESC""",
            (cutoff,),
        ).fetchall()
        # Deduplicate: keep latest per ticker
        seen = {}
        for r in rows:
            if r["ticker"] not in seen:
                seen[r["ticker"]] = dict(r)
        return list(seen.values())
    finally:
        conn.close()


def _momentum_score(ticker: str) -> float:
    """30-day risk-adjusted momentum (return / annualised vol)."""
    conn = database.get_connection()
    try:
        rows = conn.execute(
            """SELECT close FROM price_history
               WHERE ticker=? AND interval='1d' AND close IS NOT NULL
               ORDER BY date DESC LIMIT 35""",
            (ticker,),
        ).fetchall()
    finally:
        conn.close()
    closes = [r["close"] for r in rows]
    if len(closes) < 15:
        return 0.0
    closes = list(reversed(closes))
    rets = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]
    mom = (closes[-1] - closes[0]) / closes[0]
    vol = (sum(r ** 2 for r in rets) / len(rets)) ** 0.5 * (252 ** 0.5)
    return float(mom / vol) if vol > 0.001 else 0.0


def _composite_score(sig: dict, pattern_score: float, momentum: float) -> float:
    """
    Composite score in [-1, 1] combining:
      signal components (70%), pattern engine (20%), momentum (10%)
    """
    if sig["signal"] == "BUY":
        base = sig["confidence"]
    elif sig["signal"] == "SELL":
        base = -sig["confidence"]
    else:
        base = 0.0

    # Weighted signal sub-components already baked into confidence;
    # use raw sub-scores for finer ranking
    raw = (
        (sig.get("gnn_score") or 0.0) * 0.30 +
        (sig.get("xgb_score") or 0.0) * 0.22 +
        (sig.get("sentiment_score") or 0.0) * 0.18 +
        (sig.get("fundamental_score") or 0.0) * 0.15
    )
    signal_part = (base * 0.35 + raw * 0.35)
    pattern_part = pattern_score * 2 - 1  # [0,1] → [-1,1]
    momentum_capped = max(-1.0, min(1.0, momentum / 3.0))

    return signal_part * 0.70 + pattern_part * 0.20 + momentum_capped * 0.10


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_topk_portfolio(
    k: int = _DEFAULT_K,
    include_patterns: bool = True,
    min_stage: Optional[int] = None,
) -> list[dict]:
    """
    Return top-K tickers by composite score for a rotation portfolio.

    Args:
        k: Portfolio size
        include_patterns: Run pattern scan (slower but richer)
        min_stage: If set (e.g. 2), only include tickers in Weinstein Stage >= min_stage

    Returns:
        Ranked list of dicts with ticker, composite_score, signal, patterns, etc.
    """
    signals = _load_recent_signals()
    if not signals:
        logger.warning("TopK: no recent signals found")
        return []

    scored = []
    for sig in signals:
        ticker = sig["ticker"]
        if sig.get("confidence", 0) < _MIN_CONFIDENCE:
            continue

        # Pattern score
        pat_result = scan_patterns(ticker) if include_patterns else {"pattern_score": 0.0, "patterns": [], "stage": {}}
        pattern_score = pat_result.get("pattern_score", 0.0)
        stage = pat_result.get("stage", {}).get("stage", 0)

        if min_stage is not None and stage < min_stage:
            continue

        momentum = _momentum_score(ticker)
        composite = _composite_score(sig, pattern_score, momentum)

        scored.append({
            "ticker": ticker,
            "name": sig.get("name", ""),
            "sector": sig.get("sector", ""),
            "signal": sig["signal"],
            "confidence": round(sig["confidence"], 4),
            "composite_score": round(composite, 4),
            "pattern_score": pattern_score,
            "patterns": pat_result.get("patterns", []),
            "stage": stage,
            "stage_name": pat_result.get("stage", {}).get("stage_name", ""),
            "momentum_score": round(momentum, 3),
            "gnn_score": sig.get("gnn_score"),
            "xgb_score": sig.get("xgb_score"),
        })

    # Sort by composite score descending
    scored.sort(key=lambda x: x["composite_score"], reverse=True)

    # Top K long candidates + top K short (negative)
    longs = [s for s in scored if s["composite_score"] > 0][:k]
    shorts = [s for s in sorted(scored, key=lambda x: x["composite_score"])[:k] if s["composite_score"] < -0.1]

    for item in longs:
        item["position"] = "LONG"
    for item in shorts:
        item["position"] = "SHORT"

    # Attach optimized weights to long positions via PyPortfolioOpt
    if longs:
        long_tickers = [i["ticker"] for i in longs]
        weights = optimize_weights(long_tickers, method="max_sharpe")
        meta = weights.pop("_meta", {})
        for item in longs:
            item["optimal_weight"] = weights.get(item["ticker"], round(1 / len(longs), 4))
        # Attach portfolio-level stats to first item (consumed by frontend)
        if longs:
            longs[0]["_portfolio_meta"] = meta

    return longs + shorts


def get_rotation_diff(current_holdings: list[str], k: int = _DEFAULT_K) -> dict:
    """
    Given current holdings, return what to buy/sell for TopK rotation.
    """
    topk = get_topk_portfolio(k=k)
    target_tickers = {t["ticker"] for t in topk if t.get("position") == "LONG"}
    current_set = set(current_holdings)

    return {
        "add": sorted(target_tickers - current_set),
        "remove": sorted(current_set - target_tickers),
        "keep": sorted(current_set & target_tickers),
        "target_portfolio": topk,
    }
