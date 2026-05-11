"""
Risk management: Kelly position sizing, ATR stop-loss, VaR.
"""

import logging

import numpy as np
import pandas as pd

import database
from config import (
    MAX_POSITION_PCT, ATR_STOP_MULTIPLIER, RISK_REWARD_RATIO, VAR_CONFIDENCE
)

logger = logging.getLogger(__name__)


def kelly_position_size(confidence: float, portfolio_value: float) -> float:
    """
    Kelly Criterion with flat-sizing fallback.
    Kelly requires confidence > 1/(b+1) to be positive.
    Below that, fall back to confidence * MAX_POSITION_PCT (scaled flat bet).
    """
    p = min(max(confidence, 0.01), 0.99)
    b = RISK_REWARD_RATIO
    kelly_f = (p * (b + 1) - 1) / b

    if kelly_f <= 0:
        # Flat fallback: scale position by confidence, max 5% for low-confidence bets
        flat_f = confidence * MAX_POSITION_PCT * 0.5
        return portfolio_value * min(flat_f, MAX_POSITION_PCT * 0.5)

    # Half-Kelly for safety on strong signals
    kelly_f *= 0.5
    capped = min(kelly_f, MAX_POSITION_PCT)
    return portfolio_value * capped


def atr_stop_loss(entry_price: float, atr: float, direction: str = "long") -> float:
    """Stop loss at 2x ATR below entry (long) or above entry (short)."""
    if direction == "long":
        return entry_price - (ATR_STOP_MULTIPLIER * atr)
    return entry_price + (ATR_STOP_MULTIPLIER * atr)


def atr_take_profit(entry_price: float, atr: float, direction: str = "long") -> float:
    """Take profit at 3:1 risk-reward ratio."""
    risk = ATR_STOP_MULTIPLIER * atr
    reward = risk * RISK_REWARD_RATIO
    if direction == "long":
        return entry_price + reward
    return entry_price - reward


def compute_portfolio_var(holdings: list[dict], confidence: float = VAR_CONFIDENCE) -> float:
    """
    Historical VaR at given confidence level.
    holdings: list of {ticker, quantity, avg_entry}
    Returns VaR in USD (loss not exceeded with `confidence` probability).
    """
    if not holdings:
        return 0.0

    tickers = [h["ticker"] for h in holdings]
    quantities = {h["ticker"]: h["quantity"] for h in holdings}

    conn = database.get_connection()
    try:
        prices_by_ticker = {}
        for ticker in tickers:
            rows = conn.execute("""
                SELECT close FROM price_history
                WHERE ticker=? AND interval='1d'
                ORDER BY date DESC LIMIT 252
            """, (ticker,)).fetchall()
            if rows:
                prices_by_ticker[ticker] = [r["close"] for r in rows]
    finally:
        conn.close()

    portfolio_returns = []
    for i in range(1, min(252, min(len(p) for p in prices_by_ticker.values() if p) + 1)):
        daily_pnl = 0.0
        for ticker in tickers:
            prices = prices_by_ticker.get(ticker, [])
            if len(prices) > i:
                ret = (prices[i - 1] - prices[i]) / prices[i]
                qty = quantities.get(ticker, 0)
                daily_pnl += ret * qty * prices[i]
        portfolio_returns.append(daily_pnl)

    if not portfolio_returns:
        return 0.0

    portfolio_returns.sort()
    idx = int((1 - confidence) * len(portfolio_returns))
    return abs(portfolio_returns[idx])


def calculate_position(
    ticker: str,
    confidence: float,
    portfolio_value: float,
    current_price: float,
    atr: float | None,
) -> dict:
    """Full position sizing and risk levels for a trade."""
    max_invest = kelly_position_size(confidence, portfolio_value)
    quantity = max_invest / current_price if current_price > 0 else 0
    stop = atr_stop_loss(current_price, atr or current_price * 0.02) if atr else current_price * 0.98
    tp = atr_take_profit(current_price, atr or current_price * 0.02) if atr else current_price * 1.06
    risk_per_share = current_price - stop
    reward_per_share = tp - current_price

    return {
        "quantity": round(quantity, 4),
        "invest_amount": round(max_invest, 2),
        "stop_loss": round(stop, 4),
        "take_profit": round(tp, 4),
        "risk_per_share": round(risk_per_share, 4),
        "reward_per_share": round(reward_per_share, 4),
        "risk_reward": round(reward_per_share / risk_per_share, 2) if risk_per_share > 0 else 0,
    }
