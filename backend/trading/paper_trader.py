"""
Paper trading simulator. Fake wallet, real signal logic.
Executes BUY/SELL based on signals from signal_engine.
Features: trailing stop, max positions cap, time-based exit, momentum burst.
"""

import logging
import statistics
from datetime import datetime, timezone, timedelta

import database
from config import (
    PAPER_WALLET_USD, SIGNAL_CONFIDENCE_THRESHOLD,
    MAX_CONCURRENT_POSITIONS, MAX_HOLD_HOURS,
    TRAILING_STOP_PCT, MOMENTUM_BURST_PCT, MOMENTUM_VOLUME_MULT,
)
from signals.risk_engine import calculate_position

logger = logging.getLogger(__name__)


def _get_cash() -> float:
    conn = database.get_connection()
    try:
        row = conn.execute("SELECT cash_usd FROM portfolio_cash WHERE id=1").fetchone()
        if row:
            return float(row["cash_usd"])
        conn.execute("""
            INSERT INTO portfolio_cash (id, cash_usd, updated_at) VALUES (1,?,?)
        """, (PAPER_WALLET_USD, datetime.now(timezone.utc).isoformat()))
        conn.commit()
        return PAPER_WALLET_USD
    finally:
        conn.close()


def _set_cash(amount: float):
    conn = database.get_connection()
    try:
        conn.execute("""
            INSERT INTO portfolio_cash (id, cash_usd, updated_at) VALUES (1,?,?)
            ON CONFLICT(id) DO UPDATE SET cash_usd=excluded.cash_usd, updated_at=excluded.updated_at
        """, (amount, datetime.now(timezone.utc).isoformat()))
        conn.commit()
    finally:
        conn.close()


def _count_open_positions() -> int:
    conn = database.get_connection()
    try:
        return conn.execute("SELECT COUNT(*) FROM portfolio_state").fetchone()[0]
    finally:
        conn.close()


def get_portfolio_value() -> dict:
    conn = database.get_connection()
    try:
        cash = _get_cash()
        holdings = conn.execute("""
            SELECT ps.ticker, ps.quantity, ps.avg_entry, ps.stop_loss, ps.take_profit,
                   ps.highest_price, ps.opened_at,
                   ph.close AS current_price
            FROM portfolio_state ps
            LEFT JOIN (
                SELECT ticker, close FROM price_history
                WHERE interval='1d'
                AND (ticker, date) IN (
                    SELECT ticker, MAX(date) FROM price_history WHERE interval='1d' GROUP BY ticker
                )
            ) ph ON ps.ticker = ph.ticker
        """).fetchall()

        positions = []
        total_market_value = 0.0
        total_unrealized_pnl = 0.0
        for h in holdings:
            cur_price = h["current_price"] or h["avg_entry"]
            market_val = float(h["quantity"]) * float(cur_price)
            unrealized = (float(cur_price) - float(h["avg_entry"])) * float(h["quantity"])
            total_market_value += market_val
            total_unrealized_pnl += unrealized
            positions.append({
                "ticker": h["ticker"],
                "quantity": h["quantity"],
                "avg_entry": h["avg_entry"],
                "current_price": cur_price,
                "market_value": round(market_val, 2),
                "unrealized_pnl": round(unrealized, 2),
                "unrealized_pct": round((cur_price - h["avg_entry"]) / h["avg_entry"] * 100, 2) if h["avg_entry"] else 0,
                "stop_loss": h["stop_loss"],
                "take_profit": h["take_profit"],
                "opened_at": h["opened_at"],
            })

        return {
            "cash": round(cash, 2),
            "holdings_value": round(total_market_value, 2),
            "total_value": round(cash + total_market_value, 2),
            "unrealized_pnl": round(total_unrealized_pnl, 2),
            "positions": positions,
        }
    finally:
        conn.close()


def execute_buy(signal: dict):
    if signal["confidence"] < SIGNAL_CONFIDENCE_THRESHOLD:
        return
    if signal["signal"] != "BUY":
        return

    ticker = signal["ticker"]
    price = signal.get("price")
    if not price or price <= 0:
        return

    # Cap concurrent positions
    if _count_open_positions() >= MAX_CONCURRENT_POSITIONS:
        logger.debug("Max positions (%d) reached, skipping %s", MAX_CONCURRENT_POSITIONS, ticker)
        return

    portfolio = get_portfolio_value()
    cash = portfolio["cash"]
    portfolio_total = portfolio["total_value"]

    position = calculate_position(
        ticker=ticker,
        confidence=signal["confidence"],
        portfolio_value=portfolio_total,
        current_price=price,
        atr=signal.get("atr"),
    )

    if position["invest_amount"] > cash:
        logger.debug("Insufficient cash for %s: need %.2f have %.2f", ticker, position["invest_amount"], cash)
        return
    if position["quantity"] <= 0:
        return

    conn = database.get_connection()
    now = datetime.now(timezone.utc).isoformat()
    try:
        existing = conn.execute(
            "SELECT quantity, avg_entry FROM portfolio_state WHERE ticker=?", (ticker,)
        ).fetchone()

        if existing:
            old_qty = float(existing["quantity"])
            old_entry = float(existing["avg_entry"])
            new_qty = old_qty + position["quantity"]
            new_avg = (old_qty * old_entry + position["quantity"] * price) / new_qty
            conn.execute("""
                UPDATE portfolio_state
                SET quantity=?, avg_entry=?, stop_loss=?, take_profit=?, highest_price=?
                WHERE ticker=?
            """, (new_qty, new_avg, position["stop_loss"], position["take_profit"], price, ticker))
        else:
            conn.execute("""
                INSERT INTO portfolio_state
                    (ticker, quantity, avg_entry, stop_loss, take_profit, highest_price, opened_at)
                VALUES (?,?,?,?,?,?,?)
            """, (ticker, position["quantity"], price,
                  position["stop_loss"], position["take_profit"], price, now))

        conn.execute("""
            INSERT INTO paper_trades (ticker, action, quantity, price, timestamp, reason)
            VALUES (?,?,?,?,?,?)
        """, (ticker, "BUY", position["quantity"], price, now,
              f"Confidence: {signal['confidence']:.2f}"))

        # Inline cash update — same transaction, avoids second writer lock
        new_cash = cash - position["invest_amount"]
        conn.execute("""
            INSERT INTO portfolio_cash (id, cash_usd, updated_at) VALUES (1,?,?)
            ON CONFLICT(id) DO UPDATE SET cash_usd=excluded.cash_usd, updated_at=excluded.updated_at
        """, (new_cash, now))
        conn.commit()
        logger.info("BUY %s: qty=%.4f @ %.4f conf=%.2f stop=%.4f tp=%.4f",
                    ticker, position["quantity"], price, signal["confidence"],
                    position["stop_loss"], position["take_profit"])
    finally:
        conn.close()


def execute_sell(ticker: str, price: float, reason: str = "SELL signal"):
    conn = database.get_connection()
    now = datetime.now(timezone.utc).isoformat()
    try:
        pos = conn.execute(
            "SELECT quantity, avg_entry FROM portfolio_state WHERE ticker=?", (ticker,)
        ).fetchone()
        if not pos:
            return

        qty = float(pos["quantity"])
        avg_entry = float(pos["avg_entry"])
        pnl = (price - avg_entry) * qty

        conn.execute("""
            INSERT INTO paper_trades (ticker, action, quantity, price, timestamp, pnl, reason)
            VALUES (?,?,?,?,?,?,?)
        """, (ticker, "SELL", qty, price, now, pnl, reason))

        conn.execute("DELETE FROM portfolio_state WHERE ticker=?", (ticker,))

        # Inline cash update — same transaction
        cash_row = conn.execute("SELECT cash_usd FROM portfolio_cash WHERE id=1").fetchone()
        current_cash = float(cash_row["cash_usd"]) if cash_row else PAPER_WALLET_USD
        new_cash = current_cash + (qty * price)
        conn.execute("""
            INSERT INTO portfolio_cash (id, cash_usd, updated_at) VALUES (1,?,?)
            ON CONFLICT(id) DO UPDATE SET cash_usd=excluded.cash_usd, updated_at=excluded.updated_at
        """, (new_cash, now))
        conn.commit()
        logger.info("SELL %s: qty=%.4f @ %.4f PnL=%+.2f (%s)", ticker, qty, price, pnl, reason)
    finally:
        conn.close()


def evaluate_positions():
    """Check stop-loss, take-profit, trailing stop, and time-based exit."""
    conn = database.get_connection()
    try:
        rows = conn.execute("""
            SELECT ps.ticker, ps.quantity, ps.avg_entry, ps.stop_loss, ps.take_profit,
                   ps.highest_price, ps.opened_at,
                   ph.close AS current_price
            FROM portfolio_state ps
            LEFT JOIN (
                SELECT ticker, close FROM price_history
                WHERE interval='5m'
                AND (ticker, date) IN (
                    SELECT ticker, MAX(date) FROM price_history WHERE interval='5m' GROUP BY ticker
                )
            ) ph ON ps.ticker = ph.ticker
        """).fetchall()
    finally:
        conn.close()

    now = datetime.now(timezone.utc)

    for pos in rows:
        price = pos["current_price"]
        if not price:
            continue
        price = float(price)
        stop = pos["stop_loss"]
        tp = pos["take_profit"]
        highest = pos["highest_price"] or price
        opened_at = pos["opened_at"]

        # Update trailing stop: raise stop as price rises
        new_highest = max(float(highest), price)
        trailing_stop = new_highest * (1 - TRAILING_STOP_PCT)
        effective_stop = max(float(stop) if stop else 0, trailing_stop)

        # Persist updated highest_price and trailing stop
        if new_highest > float(highest):
            conn = database.get_connection()
            try:
                conn.execute("""
                    UPDATE portfolio_state
                    SET highest_price=?, stop_loss=?
                    WHERE ticker=?
                """, (new_highest, round(effective_stop, 4), pos["ticker"]))
                conn.commit()
            finally:
                conn.close()

        # Time-based exit: force sell after MAX_HOLD_HOURS
        if opened_at:
            try:
                opened_dt = datetime.fromisoformat(opened_at.replace("Z", "+00:00"))
                if (now - opened_dt) > timedelta(hours=MAX_HOLD_HOURS):
                    execute_sell(pos["ticker"], price, f"Time exit ({MAX_HOLD_HOURS}h limit)")
                    continue
            except Exception:
                pass

        # Stop-loss (trailing or original)
        if price <= effective_stop:
            execute_sell(pos["ticker"], price, f"Stop-loss @ {effective_stop:.4f} (trailing)")
        # Take-profit
        elif tp and price >= float(tp):
            execute_sell(pos["ticker"], price, f"Take-profit @ {tp:.4f}")


def scan_momentum_bursts(tickers: list[str]) -> list[dict]:
    """
    Detect momentum bursts: price >2% in one 5m candle + volume spike.
    Returns list of BUY-ready signal dicts for immediate execution.
    """
    bursts = []
    conn = database.get_connection()
    try:
        for ticker in tickers:
            rows = conn.execute("""
                SELECT open, high, low, close, volume, date
                FROM price_history
                WHERE ticker=? AND interval='5m'
                ORDER BY date DESC LIMIT 10
            """, (ticker,)).fetchall()

            if len(rows) < 5:
                continue

            latest = rows[0]
            if not latest["open"] or not latest["close"] or not latest["volume"]:
                continue

            candle_pct = (float(latest["close"]) - float(latest["open"])) / float(latest["open"])
            avg_vol = sum(float(r["volume"]) for r in rows[1:6] if r["volume"]) / 5

            if (candle_pct >= MOMENTUM_BURST_PCT and
                    avg_vol > 0 and
                    float(latest["volume"]) >= avg_vol * MOMENTUM_VOLUME_MULT):
                bursts.append({
                    "ticker": ticker,
                    "signal": "BUY",
                    "confidence": min(0.6, 0.3 + candle_pct * 5),  # scale confidence with move size
                    "price": float(latest["close"]),
                    "atr": None,
                    "reasons": [f"Momentum burst +{candle_pct:.1%} vol×{float(latest['volume'])/avg_vol:.1f}"],
                })
                logger.info("Momentum burst: %s +%.1f%% vol×%.1f",
                            ticker, candle_pct * 100, float(latest["volume"]) / avg_vol)
    finally:
        conn.close()

    return bursts


def process_signals(signals: list[dict]):
    """Process batch of signals: momentum scan, buys, sells, position eval."""
    if not signals:
        return

    tickers = [s["ticker"] for s in signals]

    # Momentum burst scan — independent of signal confidence
    bursts = scan_momentum_bursts(tickers)
    for burst in bursts:
        execute_buy(burst)

    sell_signals = {s["ticker"] for s in signals
                    if s["signal"] == "SELL" and s["confidence"] >= SIGNAL_CONFIDENCE_THRESHOLD}

    conn = database.get_connection()
    try:
        held = {r["ticker"] for r in conn.execute("SELECT ticker FROM portfolio_state").fetchall()}
    finally:
        conn.close()

    # Sell held positions with SELL signal
    for ticker in held & sell_signals:
        from data.market_fetcher import get_ohlcv
        ohlcv = get_ohlcv(ticker, interval="5m", limit=1)
        if ohlcv:
            execute_sell(ticker, ohlcv[-1]["close"], "SELL signal")

    # Buy on BUY signals
    for sig in signals:
        if sig["signal"] == "BUY":
            execute_buy(sig)

    evaluate_positions()


def get_trade_history(limit: int = 100) -> list[dict]:
    conn = database.get_connection()
    try:
        rows = conn.execute("""
            SELECT ticker, action, quantity, price, timestamp, pnl, reason
            FROM paper_trades ORDER BY timestamp DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_performance_stats() -> dict:
    conn = database.get_connection()
    try:
        trades = conn.execute("""
            SELECT ticker, action, quantity, price, pnl, timestamp
            FROM paper_trades ORDER BY timestamp ASC
        """).fetchall()
    finally:
        conn.close()

    if not trades:
        return {"total_trades": 0}

    sell_trades = [t for t in trades if t["action"] == "SELL"]
    if not sell_trades:
        return {"total_trades": len(trades), "closed_positions": 0}

    pnls = [float(t["pnl"]) for t in sell_trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    total_return = sum(pnls)
    win_rate = len(wins) / len(pnls) if pnls else 0
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = sum(losses) / len(losses) if losses else 0

    if len(pnls) > 1:
        std = statistics.stdev(pnls)
        sharpe = (sum(pnls) / len(pnls)) / std if std > 0 else 0
    else:
        sharpe = 0

    return {
        "total_trades": len(trades),
        "closed_positions": len(sell_trades),
        "total_realized_pnl": round(total_return, 2),
        "win_rate": round(win_rate, 4),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "best_trade": round(max(pnls), 2) if pnls else 0,
        "worst_trade": round(min(pnls), 2) if pnls else 0,
        "sharpe_ratio": round(sharpe, 4),
    }
