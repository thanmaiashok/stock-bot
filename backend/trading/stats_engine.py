"""
Portfolio performance statistics.

Metrics inspired by QuantStats (Apache 2.0): https://github.com/ranaroussi/quantstats
Adapted: pure numpy/pandas, no external QuantStats dependency, wired to our trade schema.

Metrics: Sharpe, Sortino, Calmar, VaR (95/99), CVaR, Profit Factor,
         Max Drawdown, Win Rate, CAGR, Omega Ratio.
"""

import math
import numpy as np
import pandas as pd
from typing import Optional


TRADING_DAYS = 252
RISK_FREE_RATE = 0.045  # 4.5% annualised, adjustable


# ---------------------------------------------------------------------------
# Core math (pure, no DB)
# ---------------------------------------------------------------------------

def _annualise(daily_ret: float) -> float:
    return (1 + daily_ret) ** TRADING_DAYS - 1


def sharpe_ratio(returns: np.ndarray, rf: float = RISK_FREE_RATE) -> float:
    """Annualised Sharpe ratio."""
    if len(returns) < 2:
        return 0.0
    daily_rf = (1 + rf) ** (1 / TRADING_DAYS) - 1
    excess = returns - daily_rf
    std = np.std(excess, ddof=1)
    if std == 0:
        return 0.0
    return float(np.mean(excess) / std * math.sqrt(TRADING_DAYS))


def sortino_ratio(returns: np.ndarray, rf: float = RISK_FREE_RATE) -> float:
    """Annualised Sortino ratio (penalises downside only)."""
    if len(returns) < 2:
        return 0.0
    daily_rf = (1 + rf) ** (1 / TRADING_DAYS) - 1
    excess = returns - daily_rf
    downside = excess[excess < 0]
    if len(downside) == 0:
        return float("inf")
    downside_std = math.sqrt(np.mean(downside ** 2))
    if downside_std == 0:
        return 0.0
    return float(np.mean(excess) / downside_std * math.sqrt(TRADING_DAYS))


def max_drawdown(equity_curve: np.ndarray) -> float:
    """Maximum drawdown as fraction (negative number)."""
    if len(equity_curve) < 2:
        return 0.0
    peak = np.maximum.accumulate(equity_curve)
    dd = (equity_curve - peak) / np.where(peak == 0, 1, peak)
    return float(dd.min())


def calmar_ratio(returns: np.ndarray, equity_curve: Optional[np.ndarray] = None) -> float:
    """Calmar = CAGR / abs(MaxDD)."""
    if len(returns) < 2:
        return 0.0
    if equity_curve is None:
        equity_curve = np.cumprod(1 + returns)
    cagr = _annualise(float(np.mean(returns)))
    mdd = abs(max_drawdown(equity_curve))
    if mdd == 0:
        return 0.0
    return float(cagr / mdd)


def value_at_risk(returns: np.ndarray, confidence: float = 0.95) -> float:
    """Historical VaR at given confidence (negative = loss)."""
    if len(returns) < 2:
        return 0.0
    return float(np.percentile(returns, (1 - confidence) * 100))


def cvar(returns: np.ndarray, confidence: float = 0.95) -> float:
    """Conditional VaR (Expected Shortfall): mean of losses beyond VaR."""
    var = value_at_risk(returns, confidence)
    tail = returns[returns <= var]
    return float(np.mean(tail)) if len(tail) > 0 else var


def profit_factor(returns: np.ndarray) -> float:
    """Gross profit / gross loss across all periods."""
    gains = returns[returns > 0].sum()
    losses = abs(returns[returns < 0].sum())
    if losses == 0:
        return float("inf") if gains > 0 else 1.0
    return float(gains / losses)


def omega_ratio(returns: np.ndarray, threshold: float = 0.0) -> float:
    """Omega ratio: probability-weighted gains vs losses relative to threshold."""
    above = (returns - threshold)
    gains = above[above > 0].sum()
    losses = abs(above[above < 0].sum())
    if losses == 0:
        return float("inf") if gains > 0 else 1.0
    return float(gains / losses)


def win_rate(trade_pnls: list[float]) -> float:
    if not trade_pnls:
        return 0.0
    wins = sum(1 for p in trade_pnls if p > 0)
    return round(wins / len(trade_pnls), 4)


def avg_win_loss_ratio(trade_pnls: list[float]) -> float:
    wins = [p for p in trade_pnls if p > 0]
    losses = [abs(p) for p in trade_pnls if p < 0]
    avg_win = np.mean(wins) if wins else 0.0
    avg_loss = np.mean(losses) if losses else 1.0
    if avg_loss == 0:
        return float("inf") if avg_win > 0 else 1.0
    return float(avg_win / avg_loss)


# ---------------------------------------------------------------------------
# High-level compute from trades list
# ---------------------------------------------------------------------------

def compute_stats(
    equity_curve: list[float],
    trade_pnls: Optional[list[float]] = None,
) -> dict:
    """
    Compute full performance stats from an equity curve (list of $ values)
    and optional list of per-trade PnL percentages.
    """
    eq = np.array(equity_curve, dtype=float)
    if len(eq) < 2:
        return {"error": "need_at_least_2_points"}

    # Daily returns from equity curve
    rets = np.diff(eq) / np.where(eq[:-1] == 0, 1, eq[:-1])

    total_return = float((eq[-1] - eq[0]) / eq[0]) if eq[0] != 0 else 0.0
    mdd = max_drawdown(eq)
    cagr = _annualise(float(np.mean(rets)))

    stats = {
        "total_return_pct": round(total_return * 100, 2),
        "cagr_pct": round(cagr * 100, 2),
        "sharpe": round(sharpe_ratio(rets), 3),
        "sortino": round(sortino_ratio(rets), 3),
        "calmar": round(calmar_ratio(rets, eq), 3),
        "max_drawdown_pct": round(mdd * 100, 2),
        "var_95_pct": round(value_at_risk(rets, 0.95) * 100, 3),
        "var_99_pct": round(value_at_risk(rets, 0.99) * 100, 3),
        "cvar_95_pct": round(cvar(rets, 0.95) * 100, 3),
        "profit_factor": round(profit_factor(rets), 3),
        "omega_ratio": round(omega_ratio(rets), 3),
        "volatility_ann_pct": round(float(np.std(rets, ddof=1)) * math.sqrt(TRADING_DAYS) * 100, 2),
        "avg_daily_return_pct": round(float(np.mean(rets)) * 100, 4),
    }

    if trade_pnls:
        stats["win_rate"] = win_rate(trade_pnls)
        stats["avg_win_loss_ratio"] = round(avg_win_loss_ratio(trade_pnls), 3)
        stats["num_trades"] = len(trade_pnls)
        stats["num_wins"] = sum(1 for p in trade_pnls if p > 0)
        stats["num_losses"] = sum(1 for p in trade_pnls if p < 0)
        stats["best_trade_pct"] = round(max(trade_pnls) * 100, 2) if trade_pnls else 0
        stats["worst_trade_pct"] = round(min(trade_pnls) * 100, 2) if trade_pnls else 0
        stats["avg_trade_pct"] = round(float(np.mean(trade_pnls)) * 100, 3)
        stats["profit_factor_trades"] = round(profit_factor(np.array(trade_pnls)), 3)

    return stats


def benchmark_compare(strategy_returns: np.ndarray, benchmark_returns: np.ndarray) -> dict:
    """Compare strategy vs benchmark (both as daily return arrays)."""
    n = min(len(strategy_returns), len(benchmark_returns))
    if n < 2:
        return {}
    s = strategy_returns[:n]
    b = benchmark_returns[:n]
    alpha_daily = float(np.mean(s) - np.mean(b))
    cov = np.cov(s, b)
    beta = float(cov[0, 1] / cov[1, 1]) if cov[1, 1] != 0 else 1.0
    alpha_ann = _annualise(alpha_daily)
    return {
        "alpha_ann_pct": round(alpha_ann * 100, 2),
        "beta": round(beta, 3),
        "correlation": round(float(np.corrcoef(s, b)[0, 1]), 3),
        "information_ratio": round(float(np.mean(s - b) / (np.std(s - b, ddof=1) + 1e-9) * math.sqrt(TRADING_DAYS)), 3),
    }
