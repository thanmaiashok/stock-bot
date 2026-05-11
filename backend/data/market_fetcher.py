"""
Batch yfinance OHLCV fetcher for all three tiers.
Tier 0: daily EOD for all filtered tickers
Tier 1: hourly intraday for top 1000
Tier 2: 15-min intraday for top 200
"""

import logging
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yfinance as yf

import database
from config import YFINANCE_BATCH_SIZE, YFINANCE_BATCH_DELAY, YFINANCE_MAX_RETRIES
from data.universe_manager import get_tickers_by_tier, get_all_active_tickers

logger = logging.getLogger(__name__)


def _download_batch(tickers: list[str], period: str, interval: str) -> dict[str, pd.DataFrame]:
    """
    Returns dict: ticker → DataFrame(date, open, high, low, close, volume).
    Handles single and multi-ticker yfinance column layout.
    """
    if not tickers:
        return {}
    for attempt in range(YFINANCE_MAX_RETRIES):
        try:
            raw = yf.download(
                tickers,
                period=period,
                interval=interval,
                group_by="ticker",
                auto_adjust=True,
                progress=False,
                threads=True,
            )
            break
        except Exception as exc:
            wait = 2 ** attempt
            logger.warning("yfinance download attempt %d failed: %s. Retry in %ds", attempt + 1, exc, wait)
            time.sleep(wait)
    else:
        return {}

    result = {}
    if len(tickers) == 1:
        ticker = tickers[0]
        if "Close" in raw.columns:
            result[ticker] = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
            result[ticker].columns = ["open", "high", "low", "close", "volume"]
    else:
        for ticker in tickers:
            try:
                if ticker not in raw.columns.get_level_values(0):
                    continue
                sub = raw[ticker][["Open", "High", "Low", "Close", "Volume"]].copy()
                sub.columns = ["open", "high", "low", "close", "volume"]
                sub = sub.dropna(subset=["close"])
                if not sub.empty:
                    result[ticker] = sub
            except Exception:
                pass
    return result


def _store_price_data(ticker_data: dict[str, pd.DataFrame], interval: str):
    conn = database.get_connection()
    now = datetime.now(timezone.utc).isoformat()
    try:
        cur = conn.cursor()
        for ticker, df in ticker_data.items():
            for ts, row in df.iterrows():
                date_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
                cur.execute("""
                    INSERT OR REPLACE INTO price_history
                        (ticker, date, interval, open, high, low, close, volume)
                    VALUES (?,?,?,?,?,?,?,?)
                """, (
                    ticker, date_str, interval,
                    _safe_float(row["open"]),
                    _safe_float(row["high"]),
                    _safe_float(row["low"]),
                    _safe_float(row["close"]),
                    _safe_float(row["volume"]),
                ))
        conn.commit()
    finally:
        conn.close()


def _safe_float(val) -> float | None:
    try:
        f = float(val)
        return None if pd.isna(f) else f
    except Exception:
        return None


def _run_batched(tickers: list[str], period: str, interval: str, label: str):
    logger.info("[%s] Fetching %d tickers period=%s interval=%s", label, len(tickers), period, interval)
    total_stored = 0
    for i in range(0, len(tickers), YFINANCE_BATCH_SIZE):
        batch = tickers[i: i + YFINANCE_BATCH_SIZE]
        data = _download_batch(batch, period, interval)
        _store_price_data(data, interval)
        total_stored += len(data)
        logger.debug("[%s] Batch %d/%d: got data for %d/%d tickers",
                     label, i // YFINANCE_BATCH_SIZE + 1,
                     (len(tickers) - 1) // YFINANCE_BATCH_SIZE + 1,
                     len(data), len(batch))
        time.sleep(YFINANCE_BATCH_DELAY)
    logger.info("[%s] Done. Stored data for %d tickers", label, total_stored)


def fetch_tier0_eod():
    """Daily EOD: all filtered tickers, 1d interval. First run fetches 1y history; subsequent runs top-up 5d."""
    tickers = get_all_active_tickers()
    conn = database.get_connection()
    try:
        max_per_ticker = conn.execute(
            "SELECT MAX(cnt) FROM (SELECT COUNT(*) cnt FROM price_history WHERE interval='1d' GROUP BY ticker)"
        ).fetchone()[0] or 0
    finally:
        conn.close()
    period = "5d" if max_per_ticker > 60 else "1y"
    _run_batched(tickers, period, "1d", "Tier0-EOD")


def fetch_tier1_intraday():
    """Hourly: Tier 1 tickers, 1h interval."""
    tickers = get_tickers_by_tier(2) + get_tickers_by_tier(1)
    _run_batched(tickers, "5d", "1h", "Tier1-1h")


def fetch_tier2_intraday():
    """15-min: Tier 2 (deep analysis) tickers."""
    tickers = get_tickers_by_tier(2)
    _run_batched(tickers, "2d", "15m", "Tier2-15m")


def fetch_tier2_5min():
    """5-min candles: Tier 2 tickers. No API key — yfinance only."""
    tickers = get_tickers_by_tier(2)
    _run_batched(tickers, "1d", "5m", "Tier2-5m")


def compute_price_correlations(min_corr: float = 0.50, days: int = 30):
    """
    Compute real Pearson correlations between Tier 2 tickers from price_history.
    Stores pairs with |corr| >= min_corr in price_correlations table.
    """
    tickers = get_tickers_by_tier(2)
    logger.info("Computing correlations for %d tickers (last %d days)", len(tickers), days)

    conn = database.get_connection()
    try:
        price_series = {}
        for ticker in tickers:
            rows = conn.execute("""
                SELECT date, close FROM price_history
                WHERE ticker=? AND interval='1d' AND close IS NOT NULL
                ORDER BY date DESC LIMIT ?
            """, (ticker, days)).fetchall()
            if len(rows) >= 10:
                closes = [r["close"] for r in reversed(rows)]
                price_series[ticker] = np.array(closes, dtype=float)
    finally:
        conn.close()

    valid = list(price_series.keys())
    logger.info("Computing %d×%d correlation matrix", len(valid), len(valid))

    # Compute daily returns
    returns = {}
    for t, prices in price_series.items():
        if len(prices) >= 2:
            ret = np.diff(prices) / (prices[:-1] + 1e-10)
            returns[t] = ret

    valid = list(returns.keys())
    pairs = []
    for i, t1 in enumerate(valid):
        for t2 in valid[i+1:]:
            r1, r2 = returns[t1], returns[t2]
            n = min(len(r1), len(r2))
            if n < 5:
                continue
            corr = float(np.corrcoef(r1[-n:], r2[-n:])[0, 1])
            if np.isnan(corr):
                continue
            if abs(corr) >= min_corr:
                # Always store with smaller ticker first for consistent key
                a, b = sorted([t1, t2])
                pairs.append((a, b, round(corr, 4)))

    now = datetime.now(timezone.utc).isoformat()
    conn = database.get_connection()
    try:
        conn.execute("DELETE FROM price_correlations")
        conn.executemany("""
            INSERT OR REPLACE INTO price_correlations (ticker1, ticker2, correlation, updated_at)
            VALUES (?,?,?,?)
        """, [(a, b, c, now) for a, b, c in pairs])
        conn.commit()
        logger.info("Stored %d real correlation pairs (|r|>=%.2f)", len(pairs), min_corr)
    finally:
        conn.close()

    return len(pairs)


def fetch_tickers_now(tickers: list[str], interval: str = "5m", period: str = "1d"):
    """On-demand fetch for specific tickers — news hit or hot signal."""
    if not tickers:
        return
    # Deduplicate, cap at 50 to stay rate-limit safe
    tickers = list(set(tickers))[:50]
    _run_batched(tickers, period, interval, f"OnDemand-{interval}")


def get_ohlcv(ticker: str, interval: str = "1d", limit: int = 200) -> list[dict]:
    conn = database.get_connection()
    try:
        rows = conn.execute("""
            SELECT date, open, high, low, close, volume
            FROM price_history
            WHERE ticker=? AND interval=?
            ORDER BY date DESC LIMIT ?
        """, (ticker, interval, limit)).fetchall()
        return [dict(r) for r in reversed(rows)]
    finally:
        conn.close()
