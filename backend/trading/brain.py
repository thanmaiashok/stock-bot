"""
TradingBrain — self-learning signal weight optimizer.

Algorithm:
  Policy-gradient update after every closed trade:
    w_i += LR * outcome * component_i
  where:
    outcome   = pnl_pct / AVG_ABS_PNL, clipped to [-1, +1]
    component = raw (pre-weight) score that the signal engine produced

  Weights are clipped to [W_MIN, W_MAX] then renormalized to sum=1.

Regime detection (run every REGIME_INTERVAL seconds):
  Uses last-20-close prices of ES=F (or cross-instrument average) to classify:
    TRENDING  → |ema5 - ema20| / price > 0.8%
    VOLATILE  → realised_vol > 2% daily
    RANGING   → otherwise

  Regime shifts apply a one-shot nudge to weights:
    TRENDING  → momentum ↑, ema ↑, rsi ↓
    RANGING   → rsi ↑, bbands ↑, momentum ↓
    VOLATILE  → bbands ↑, consistency ↑

Brain state persists in brain_state table.
Every 10 learning episodes → snapshot appended to brain_log.
"""

import json
import logging
import time
from datetime import datetime, timezone

import database

logger = logging.getLogger(__name__)

# ── Hyperparameters ──────────────────────────────────────────────────────────
LR              = 0.015    # per-trade learning rate (slow & stable)
REGIME_LR       = 0.025    # one-shot regime nudge magnitude
W_MIN           = 0.05     # floor: no component below 5%
W_MAX           = 0.60     # ceiling: no component dominates > 60%
AVG_ABS_PNL     = 3.0      # normalizer for P&L → outcome in [-1,+1]
LOG_EVERY       = 5        # append brain_log every N episodes
REGIME_INTERVAL = 1800     # re-detect regime every 30 min

_last_regime_check: float = 0.0

DEFAULT_W = {
    "momentum":    0.30,
    "ema":         0.25,
    "rsi":         0.20,
    "bbands":      0.15,
    "consistency": 0.10,
}

REGIME_NUDGE = {
    "TRENDING": {"momentum": +0.04, "ema": +0.03, "rsi": -0.03, "bbands": -0.02, "consistency": -0.02},
    "RANGING":  {"rsi": +0.04, "bbands": +0.03, "momentum": -0.04, "ema": -0.02, "consistency": -0.01},
    "VOLATILE": {"bbands": +0.04, "consistency": +0.03, "momentum": -0.03, "ema": -0.02, "rsi": -0.02},
}


# ── State I/O ────────────────────────────────────────────────────────────────

def _load_state(conn) -> dict:
    row = conn.execute("SELECT * FROM brain_state WHERE id=1").fetchone()
    if not row:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT INTO brain_state
               (id, momentum_w, ema_w, rsi_w, bbands_w, consistency_w,
                learning_episodes, recent_win_rate, regime, updated_at)
               VALUES (1, 0.30, 0.25, 0.20, 0.15, 0.10, 0, 0.5, 'UNKNOWN', ?)""",
            (now,),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM brain_state WHERE id=1").fetchone()
    return dict(row)


def _save_state(conn, state: dict):
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO brain_state
           (id, momentum_w, ema_w, rsi_w, bbands_w, consistency_w,
            learning_episodes, recent_win_rate, regime, updated_at)
           VALUES (1, :momentum_w, :ema_w, :rsi_w, :bbands_w, :consistency_w,
                   :learning_episodes, :recent_win_rate, :regime, :updated_at)
           ON CONFLICT(id) DO UPDATE SET
               momentum_w=excluded.momentum_w,
               ema_w=excluded.ema_w,
               rsi_w=excluded.rsi_w,
               bbands_w=excluded.bbands_w,
               consistency_w=excluded.consistency_w,
               learning_episodes=excluded.learning_episodes,
               recent_win_rate=excluded.recent_win_rate,
               regime=excluded.regime,
               updated_at=excluded.updated_at""",
        {**state, "updated_at": now},
    )
    conn.commit()


def _append_log(conn, state: dict):
    conn.execute(
        """INSERT INTO brain_log
           (momentum_w, ema_w, rsi_w, bbands_w, consistency_w,
            win_rate, regime, episode, timestamp)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            state["momentum_w"], state["ema_w"], state["rsi_w"],
            state["bbands_w"], state["consistency_w"],
            state["recent_win_rate"], state["regime"],
            state["learning_episodes"],
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()


def _normalize(weights: dict) -> dict:
    keys = ["momentum", "ema", "rsi", "bbands", "consistency"]
    # Clip to bounds
    clipped = {k: max(W_MIN, min(W_MAX, weights[k])) for k in keys}
    total = sum(clipped.values())
    return {k: round(clipped[k] / total, 5) for k in keys}


# ── Public API ───────────────────────────────────────────────────────────────

def get_weights() -> dict:
    """Return current learned weights (falls back to defaults if DB empty)."""
    conn = database.get_connection()
    try:
        state = _load_state(conn)
    finally:
        conn.close()
    return {
        "momentum":    state["momentum_w"],
        "ema":         state["ema_w"],
        "rsi":         state["rsi_w"],
        "bbands":      state["bbands_w"],
        "consistency": state["consistency_w"],
    }


def record_outcome(components: dict, pnl_pct: float, direction: str):
    """
    Called when a trade closes. Performs one gradient step.

    components: raw (pre-weight) component scores from _compute_signal
                {"momentum": float, "ema": float, "rsi": float,
                 "bbands": float, "consistency": float}
    pnl_pct:    realised % gain/loss (e.g. +4.2 or -2.1)
    direction:  "long" | "short"
    """
    if not components:
        return

    conn = database.get_connection()
    try:
        state = _load_state(conn)

        # Outcome in [-1, +1]
        outcome = max(-1.0, min(1.0, pnl_pct / AVG_ABS_PNL))
        # For short positions: component sign flips (positive mom_score → SHORT conviction)
        dir_sign = 1.0 if direction == "long" else -1.0

        keys = ["momentum", "ema", "rsi", "bbands", "consistency"]
        w_map = {
            "momentum":    state["momentum_w"],
            "ema":         state["ema_w"],
            "rsi":         state["rsi_w"],
            "bbands":      state["bbands_w"],
            "consistency": state["consistency_w"],
        }

        for k in keys:
            c = float(components.get(k, 0.0)) * dir_sign
            w_map[k] += LR * outcome * c

        w_map = _normalize(w_map)

        # Update recent win rate (exponential moving average)
        win = 1.0 if pnl_pct > 0 else 0.0
        alpha = 0.15
        new_wr = alpha * win + (1 - alpha) * float(state["recent_win_rate"])

        episodes = state["learning_episodes"] + 1
        state.update({
            "momentum_w":        w_map["momentum"],
            "ema_w":             w_map["ema"],
            "rsi_w":             w_map["rsi"],
            "bbands_w":          w_map["bbands"],
            "consistency_w":     w_map["consistency"],
            "learning_episodes": episodes,
            "recent_win_rate":   round(new_wr, 4),
        })
        _save_state(conn, state)

        if episodes % LOG_EVERY == 0:
            _append_log(conn, state)

        logger.info("Brain learned: outcome=%.2f, episodes=%d, weights=%s",
                    outcome, episodes, {k: round(w_map[k], 3) for k in keys})
    except Exception as exc:
        logger.error("Brain record_outcome failed: %s", exc)
    finally:
        conn.close()


def detect_and_apply_regime():
    """
    Detect current market regime from recent futures price data.
    Applies a one-shot nudge to weights if regime changed.
    Runs at most once per REGIME_INTERVAL seconds.
    """
    global _last_regime_check
    if time.time() - _last_regime_check < REGIME_INTERVAL:
        return
    _last_regime_check = time.time()

    try:
        import yfinance as yf
        import numpy as np

        # Use S&P futures (ES=F) as regime proxy
        hist = yf.Ticker("ES=F").history(period="25d", interval="1d")
        closes = hist["Close"].dropna().values.astype(float)
        if len(closes) < 10:
            return

        # EMA 5 vs 20 for trend
        s = list(closes)
        ema5 = s[0]; ema20 = s[0]
        for p in s:
            ema5  = 2/6  * p + (1 - 2/6)  * ema5
            ema20 = 2/21 * p + (1 - 2/21) * ema20

        trend_strength = abs(ema5 - ema20) / (ema20 + 1e-9)

        # Realised daily vol
        rets = np.diff(closes) / closes[:-1]
        daily_vol = float(np.std(rets[-10:]))

        if daily_vol > 0.02:
            regime = "VOLATILE"
        elif trend_strength > 0.008:
            regime = "TRENDING"
        else:
            regime = "RANGING"

        conn = database.get_connection()
        try:
            state = _load_state(conn)
            old_regime = state["regime"]

            if regime != old_regime and old_regime != "UNKNOWN":
                nudge = REGIME_NUDGE.get(regime, {})
                w_map = {
                    "momentum":    state["momentum_w"],
                    "ema":         state["ema_w"],
                    "rsi":         state["rsi_w"],
                    "bbands":      state["bbands_w"],
                    "consistency": state["consistency_w"],
                }
                for k, delta in nudge.items():
                    w_map[k] += REGIME_LR * delta
                w_map = _normalize(w_map)
                state.update({
                    "momentum_w":    w_map["momentum"],
                    "ema_w":         w_map["ema"],
                    "rsi_w":         w_map["rsi"],
                    "bbands_w":      w_map["bbands"],
                    "consistency_w": w_map["consistency"],
                })
                logger.info("Brain regime change: %s → %s, weights nudged", old_regime, regime)
                _append_log(conn, {**state, "regime": regime})

            state["regime"] = regime
            _save_state(conn, state)
        finally:
            conn.close()

    except Exception as exc:
        logger.debug("Brain regime detection failed: %s", exc)


def get_brain_state() -> dict:
    """Full brain state for API/display."""
    conn = database.get_connection()
    try:
        state = _load_state(conn)
        log_rows = conn.execute(
            "SELECT * FROM brain_log ORDER BY id DESC LIMIT 100"
        ).fetchall()
        log = list(reversed([dict(r) for r in log_rows]))

        # Recent trade stats
        recent = conn.execute(
            """SELECT pnl FROM futures_trades
               WHERE action='CLOSE' AND pnl IS NOT NULL
               ORDER BY timestamp DESC LIMIT 30"""
        ).fetchall()
        pnls = [float(r["pnl"]) for r in recent]
        wins = [p for p in pnls if p > 0]

        return {
            "weights": {
                "momentum":    round(state["momentum_w"], 4),
                "ema":         round(state["ema_w"], 4),
                "rsi":         round(state["rsi_w"], 4),
                "bbands":      round(state["bbands_w"], 4),
                "consistency": round(state["consistency_w"], 4),
            },
            "learning_episodes":  state["learning_episodes"],
            "recent_win_rate":    round(float(state["recent_win_rate"]) * 100, 1),
            "regime":             state["regime"],
            "updated_at":         state["updated_at"],
            "recent_trades":      len(pnls),
            "recent_pnl":         round(sum(pnls), 2),
            "history":            log,
            "defaults":           DEFAULT_W,
        }
    finally:
        conn.close()
