"""
Paper futures trader.
Long/Short positions with 10x simulated leverage.
Margin = 10% of notional (1 / leverage).
Auto stop-loss: 2% against. Auto take-profit: 4% in favor (2:1 R/R).
"""

import logging
from datetime import datetime, timezone

import database

logger = logging.getLogger(__name__)

FUTURES_INITIAL_CASH = 10_000.0
LEVERAGE = 10
STOP_LOSS_PCT   = 0.02   # 2% of notional
TAKE_PROFIT_PCT = 0.04   # 4% of notional
MARGIN_RATE     = 1 / LEVERAGE  # 0.10


# ---------------------------------------------------------------------------
# Cash helpers
# ---------------------------------------------------------------------------

def _get_cash() -> float:
    conn = database.get_connection()
    try:
        row = conn.execute("SELECT cash_usd FROM futures_cash WHERE id=1").fetchone()
        if row:
            return float(row["cash_usd"])
        conn.execute(
            "INSERT INTO futures_cash (id, cash_usd, updated_at) VALUES (1,?,?)",
            (FUTURES_INITIAL_CASH, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return FUTURES_INITIAL_CASH
    finally:
        conn.close()


def _set_cash(amount: float):
    conn = database.get_connection()
    try:
        conn.execute(
            "INSERT INTO futures_cash (id, cash_usd, updated_at) VALUES (1,?,?)"
            " ON CONFLICT(id) DO UPDATE SET cash_usd=excluded.cash_usd, updated_at=excluded.updated_at",
            (round(amount, 4), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------

def get_portfolio() -> dict:
    """All open futures positions with live P&L."""
    from data.futures_fetcher import fetch_quotes
    qmap = {q["symbol"]: q for q in fetch_quotes()}

    conn = database.get_connection()
    try:
        cash = _get_cash()
        rows = conn.execute("SELECT * FROM futures_positions").fetchall()
    finally:
        conn.close()

    positions = []
    total_margin = 0.0
    total_pnl = 0.0

    for pos in rows:
        sym       = pos["symbol"]
        direction = pos["direction"]
        entry     = float(pos["entry_price"])
        units     = float(pos["units"])
        margin    = float(pos["margin_used"])
        q         = qmap.get(sym)
        cur       = q["price"] if q else entry

        pnl = (
            (cur - entry) * units * LEVERAGE if direction == "long"
            else (entry - cur) * units * LEVERAGE
        )
        total_margin += margin
        total_pnl    += pnl

        positions.append({
            "symbol":        sym,
            "name":          (q or {}).get("name", sym),
            "category":      (q or {}).get("category", ""),
            "direction":     direction,
            "units":         units,
            "entry_price":   entry,
            "current_price": round(cur, 4),
            "notional":      round(entry * units, 2),
            "margin_used":   round(margin, 2),
            "pnl":           round(pnl, 2),
            "pnl_pct":       round(pnl / margin * 100, 2) if margin > 0 else 0,
            "stop_loss":     pos["stop_loss"],
            "take_profit":   pos["take_profit"],
            "opened_at":     pos["opened_at"],
        })

    return {
        "cash":        round(cash, 2),
        "margin_used": round(total_margin, 2),
        "total_pnl":   round(total_pnl, 2),
        "equity":      round(cash + total_pnl, 2),
        "leverage":    LEVERAGE,
        "positions":   positions,
    }


# ---------------------------------------------------------------------------
# Open / Close
# ---------------------------------------------------------------------------

def open_position(symbol: str, direction: str, units: float, price: float,
                  components: dict | None = None) -> dict:
    """
    Open a paper futures position.
    direction: "long" | "short"
    units: number of units (e.g. 1.0 = 1 barrel for CL=F)
    price: current market price
    """
    direction = direction.lower()
    if direction not in ("long", "short"):
        return {"ok": False, "message": "direction must be 'long' or 'short'"}
    if units <= 0 or price <= 0:
        return {"ok": False, "message": "units and price must be positive"}

    notional = price * units
    margin   = round(notional * MARGIN_RATE, 4)
    cash     = _get_cash()

    if margin > cash:
        return {"ok": False, "message": f"Need ${margin:.2f} margin — only ${cash:.2f} available"}

    if direction == "long":
        sl = round(price * (1 - STOP_LOSS_PCT), 4)
        tp = round(price * (1 + TAKE_PROFIT_PCT), 4)
    else:
        sl = round(price * (1 + STOP_LOSS_PCT), 4)
        tp = round(price * (1 - TAKE_PROFIT_PCT), 4)

    now  = datetime.now(timezone.utc).isoformat()
    conn = database.get_connection()
    try:
        existing = conn.execute(
            "SELECT units, margin_used, entry_price FROM futures_positions WHERE symbol=? AND direction=?",
            (symbol, direction),
        ).fetchone()

        import json as _json
        snap = _json.dumps(components or {})

        if existing:
            old_qty    = float(existing["units"])
            old_margin = float(existing["margin_used"])
            old_entry  = float(existing["entry_price"])
            new_qty    = old_qty + units
            new_entry  = (old_qty * old_entry + units * price) / new_qty
            conn.execute(
                "UPDATE futures_positions"
                " SET units=?, margin_used=?, entry_price=?, updated_at=?, components_snapshot=?"
                " WHERE symbol=? AND direction=?",
                (new_qty, old_margin + margin, round(new_entry, 4), now, snap, symbol, direction),
            )
        else:
            conn.execute(
                "INSERT INTO futures_positions"
                " (symbol, direction, units, entry_price, margin_used, stop_loss, take_profit,"
                "  opened_at, updated_at, components_snapshot)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (symbol, direction, units, price, margin, sl, tp, now, now, snap),
            )

        conn.execute(
            "INSERT INTO futures_trades"
            " (symbol, direction, action, units, price, margin, timestamp, reason, components_snapshot)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (symbol, direction, "OPEN", units, price, margin, now, "Manual order", snap),
        )
        conn.commit()
    finally:
        conn.close()

    _set_cash(cash - margin)
    logger.info("Futures OPEN %s %s %.4f @ %.4f margin=%.2f", direction.upper(), symbol, units, price, margin)
    return {
        "ok":      True,
        "margin":  margin,
        "sl":      sl,
        "tp":      tp,
        "message": f"Opened {direction} {units} {symbol} @ {price:.4f}",
    }


def close_position(symbol: str, current_price: float, reason: str = "Manual") -> dict:
    """Close an open futures position and realize P&L."""
    import json as _json
    conn = database.get_connection()
    try:
        pos = conn.execute(
            "SELECT * FROM futures_positions WHERE symbol=?", (symbol,)
        ).fetchone()
        if not pos:
            return {"ok": False, "message": f"No open position for {symbol}"}

        direction  = pos["direction"]
        entry      = float(pos["entry_price"])
        units      = float(pos["units"])
        margin     = float(pos["margin_used"])
        components = {}
        try:
            components = _json.loads(pos["components_snapshot"] or "{}")
        except Exception:
            pass

        pnl = (
            (current_price - entry) * units * LEVERAGE if direction == "long"
            else (entry - current_price) * units * LEVERAGE
        )
        now = datetime.now(timezone.utc).isoformat()
        snap = _json.dumps(components)

        conn.execute(
            "INSERT INTO futures_trades"
            " (symbol, direction, action, units, price, margin, pnl, timestamp, reason, components_snapshot)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (symbol, direction, "CLOSE", units, current_price, margin, round(pnl, 4), now, reason, snap),
        )
        conn.execute("DELETE FROM futures_positions WHERE symbol=?", (symbol,))
        conn.commit()
    finally:
        conn.close()

    _set_cash(_get_cash() + margin + pnl)
    logger.info("Futures CLOSE %s PnL=%+.2f (%s)", symbol, pnl, reason)

    # Brain learns from this trade outcome
    if components:
        pnl_pct = pnl / (margin + 1e-9) * 100
        try:
            from trading.brain import record_outcome, detect_and_apply_regime
            record_outcome(components, pnl_pct, direction)
            detect_and_apply_regime()
        except Exception as exc:
            logger.debug("Brain update skipped: %s", exc)

    return {"ok": True, "pnl": round(pnl, 2), "message": f"Closed {symbol} PnL={pnl:+.2f}"}


# ---------------------------------------------------------------------------
# Auto stop/take-profit eval
# ---------------------------------------------------------------------------

def evaluate_futures_positions():
    """Check stop-loss and take-profit for all open positions. Run every 30s."""
    from data.futures_fetcher import fetch_quotes
    qmap = {q["symbol"]: q for q in fetch_quotes()}

    conn = database.get_connection()
    try:
        positions = conn.execute("SELECT * FROM futures_positions").fetchall()
    finally:
        conn.close()

    for pos in positions:
        q = qmap.get(pos["symbol"])
        if not q:
            continue
        cur       = q["price"]
        direction = pos["direction"]
        sl        = float(pos["stop_loss"])  if pos["stop_loss"]  else None
        tp        = float(pos["take_profit"]) if pos["take_profit"] else None

        if direction == "long":
            if sl and cur <= sl:
                close_position(pos["symbol"], cur, f"Stop-loss @ {sl:.4f}")
            elif tp and cur >= tp:
                close_position(pos["symbol"], cur, f"Take-profit @ {tp:.4f}")
        else:
            if sl and cur >= sl:
                close_position(pos["symbol"], cur, f"Stop-loss @ {sl:.4f}")
            elif tp and cur <= tp:
                close_position(pos["symbol"], cur, f"Take-profit @ {tp:.4f}")


# ---------------------------------------------------------------------------
# History / stats
# ---------------------------------------------------------------------------

def get_trade_history(limit: int = 50) -> list[dict]:
    conn = database.get_connection()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM futures_trades ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()]
    finally:
        conn.close()


def get_performance() -> dict:
    conn = database.get_connection()
    try:
        pnls = [float(r["pnl"]) for r in conn.execute(
            "SELECT pnl FROM futures_trades WHERE action='CLOSE' AND pnl IS NOT NULL"
        ).fetchall()]
    finally:
        conn.close()

    if not pnls:
        return {"closed": 0, "total_pnl": 0.0, "win_rate": 0.0, "best": 0.0, "worst": 0.0}

    wins = [p for p in pnls if p > 0]
    return {
        "closed":    len(pnls),
        "total_pnl": round(sum(pnls), 2),
        "win_rate":  round(len(wins) / len(pnls), 3),
        "avg_pnl":   round(sum(pnls) / len(pnls), 2),
        "best":      round(max(pnls), 2),
        "worst":     round(min(pnls), 2),
    }
