"""
FINRA REG SHO short interest fetcher. No API key needed.
Source: FINRA free public data — https://www.finra.org/filing-reporting/regulatory-filing-systems/short-interest

FINRA publishes bimonthly short interest for all US equity markets.
Short Interest Ratio (SIR) = shares short / avg daily volume (also called "Days to Cover").
High SIR (>10 days) + bullish signal = short squeeze setup.

Data URL pattern (no auth required):
  https://cdn.finra.org/equity/regsho/monthly/CNMSshvol{YYYYMMDD}.txt
"""

import csv
import io
import logging
import time
from datetime import datetime, timezone, timedelta

import requests

import database

logger = logging.getLogger(__name__)

FINRA_BASE = "https://cdn.finra.org/equity/regsho/monthly"
HEADERS = {"User-Agent": "StockBot/1.0 research@stockbot.local"}

# Known monthly settlement dates (mid-month and end-of-month)
# FINRA files: CNMSshvol{YYYYMMDD}.txt (CNMS = consolidated)
# We try the last 3 known release date patterns


def _candidate_dates() -> list[str]:
    """Generate candidate FINRA release dates (15th and last day of recent months)."""
    dates = []
    now = datetime.now(timezone.utc)
    for month_offset in range(3):
        d = now - timedelta(days=30 * month_offset)
        # Try 15th and end-of-month
        for day in [15, 28, 29, 30, 31]:
            try:
                candidate = datetime(d.year, d.month, day)
                if candidate <= now:
                    dates.append(candidate.strftime("%Y%m%d"))
            except ValueError:
                pass
    return dates


def _fetch_finra_file(date_str: str) -> list[dict]:
    """Fetch FINRA short interest file for a given date."""
    url = f"{FINRA_BASE}/CNMSshvol{date_str}.txt"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        reader = csv.DictReader(io.StringIO(resp.text), delimiter="|")
        rows = []
        for row in reader:
            ticker = row.get("Symbol", "").strip().upper()
            if not ticker or len(ticker) > 6:
                continue
            try:
                short_vol = float(row.get("ShortVolume", 0) or 0)
                total_vol = float(row.get("TotalVolume", 0) or 0)
                if total_vol > 0:
                    short_pct = round(short_vol / total_vol * 100, 2)
                else:
                    short_pct = 0.0
                rows.append({
                    "ticker": ticker,
                    "short_volume": short_vol,
                    "total_volume": total_vol,
                    "short_pct": short_pct,
                    "date": date_str,
                })
            except (ValueError, TypeError):
                continue
        logger.info("FINRA short interest: %d rows from %s", len(rows), date_str)
        return rows
    except Exception as exc:
        logger.debug("FINRA file %s failed: %s", date_str, exc)
        return []


def _store_short_interest(rows: list[dict]):
    if not rows:
        return
    conn = database.get_connection()
    try:
        cur = conn.cursor()
        for row in rows:
            cur.execute("""
                INSERT OR REPLACE INTO short_interest
                    (ticker, short_volume, total_volume, short_pct, date)
                VALUES (?,?,?,?,?)
            """, (row["ticker"], row["short_volume"], row["total_volume"],
                  row["short_pct"], row["date"]))
        conn.commit()
        logger.info("Stored %d short interest records", len(rows))
    finally:
        conn.close()


def fetch_short_interest():
    """Fetch latest available FINRA short interest data."""
    _ensure_table()
    for date_str in _candidate_dates():
        rows = _fetch_finra_file(date_str)
        if rows:
            _store_short_interest(rows)
            return len(rows)
        time.sleep(0.5)
    logger.warning("No FINRA short interest file found for recent dates")
    return 0


def get_short_interest_score(ticker: str) -> tuple[float, dict]:
    """
    Short interest signal score in [-1, 1].

    Short squeeze setup (bullish): high short % + rising price = positive
    Heavily shorted with bearish trend = negative

    Returns (score, metadata_dict).
    """
    _ensure_table()
    base = ticker.split(".")[0].upper()
    conn = database.get_connection()
    try:
        row = conn.execute("""
            SELECT short_pct, short_volume, total_volume, date
            FROM short_interest
            WHERE ticker=?
            ORDER BY date DESC LIMIT 1
        """, (base,)).fetchone()
    finally:
        conn.close()

    if not row:
        return 0.0, {}

    short_pct = float(row["short_pct"])
    meta = {
        "short_pct": short_pct,
        "short_volume": row["short_volume"],
        "total_volume": row["total_volume"],
        "as_of": row["date"],
    }

    # Score: high short % is ambiguous — could mean squeeze candidate (bullish) or
    # fundamental problem (bearish). We treat it as squeeze potential (+) when >20%,
    # and neutral-negative when 10-20%.
    # Let signal_engine combine with directional signal to interpret squeeze context.
    if short_pct > 30:
        score = 0.4   # extreme short — squeeze coil loaded
    elif short_pct > 20:
        score = 0.2
    elif short_pct > 10:
        score = 0.0   # elevated but ambiguous
    else:
        score = 0.0   # normal level, no signal

    return score, meta


def _ensure_table():
    conn = database.get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS short_interest (
                ticker TEXT NOT NULL,
                short_volume REAL,
                total_volume REAL,
                short_pct REAL,
                date TEXT NOT NULL,
                PRIMARY KEY (ticker, date)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_si_ticker ON short_interest(ticker)")
        conn.commit()
    finally:
        conn.close()
