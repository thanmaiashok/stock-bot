"""
SEC Form 4 insider trading fetcher. No API key needed.
Source: SEC EDGAR full-text search API (public domain data).

Form 4 = Statement of Changes in Beneficial Ownership
Filed by directors, officers, >10% shareholders within 2 business days of trade.
Academic evidence: insider purchases predict 5-10% abnormal returns (Lakonishok & Lee 2001).

Adapted from SEC EDGAR API docs (public domain) + open-source edgar-parser patterns.
"""

import logging
import time
from datetime import datetime, timezone, timedelta

import requests

import database

logger = logging.getLogger(__name__)

EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
EDGAR_BASE_URL = "https://www.sec.gov"

HEADERS = {
    "User-Agent": "StockBot/1.0 research@stockbot.local",
    "Accept": "application/json",
}

# Transaction codes (Form 4 field transactionCode):
# P = Purchase (open market buy) — strongly bullish
# S = Sale — bearish signal
# A = Award (granted, not bought) — neutral
# F = Tax withholding — ignore
# M = Option exercise — neutral
BULLISH_CODES = {"P"}
BEARISH_CODES = {"S"}


def _fetch_form4_filings(days_back: int = 3) -> list[dict]:
    """Fetch recent Form 4 filings from EDGAR full-text search."""
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=days_back)
    params = {
        "q": "",
        "forms": "4",
        "dateRange": "custom",
        "startdt": start_date.isoformat(),
        "enddt": end_date.isoformat(),
        "hits.hits.total.value": 1,
        "hits.hits._source.period_of_report": 1,
    }
    try:
        resp = requests.get(EDGAR_SEARCH_URL, params=params, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        hits = data.get("hits", {}).get("hits", [])
        return hits
    except Exception as exc:
        logger.warning("EDGAR Form 4 search failed: %s", exc)
        return []


def _parse_filing(filing: dict) -> list[dict]:
    """
    Extract transactions from a Form 4 filing hit.
    Returns list of {ticker, insider_name, title, transaction_type, shares, price, date}.
    """
    source = filing.get("_source", {})
    ticker = source.get("issuerTradingSymbol", "")
    if not ticker:
        return []

    ticker = ticker.upper().strip()
    period = source.get("period_of_report", "")
    filer = source.get("displayNames", ["Unknown"])
    filer_name = filer[0] if filer else "Unknown"

    # Transaction details embedded in source
    trans_type = source.get("transaction_type", "")
    shares_raw = source.get("transactionShares", 0)
    price_raw = source.get("transactionPricePerShare", 0)

    try:
        shares = float(shares_raw or 0)
        price = float(price_raw or 0)
    except (TypeError, ValueError):
        shares = 0.0
        price = 0.0

    if shares == 0:
        return []

    return [{
        "ticker": ticker,
        "insider_name": filer_name,
        "transaction_code": trans_type,
        "shares": shares,
        "price": price,
        "value_usd": shares * price,
        "date": period,
        "is_buy": trans_type in BULLISH_CODES,
        "is_sell": trans_type in BEARISH_CODES,
    }]


def _store_transactions(transactions: list[dict]):
    if not transactions:
        return
    conn = database.get_connection()
    try:
        cur = conn.cursor()
        for tx in transactions:
            cur.execute("""
                INSERT OR IGNORE INTO insider_trades
                    (ticker, insider_name, transaction_code, shares, price,
                     value_usd, trade_date, is_buy)
                VALUES (?,?,?,?,?,?,?,?)
            """, (
                tx["ticker"], tx["insider_name"], tx["transaction_code"],
                tx["shares"], tx["price"], tx["value_usd"],
                tx["date"], 1 if tx["is_buy"] else 0,
            ))
        conn.commit()
        logger.info("Stored %d insider transactions", len(transactions))
    finally:
        conn.close()


def fetch_recent_insider_trades(days_back: int = 5):
    """Main entry point: fetch + store recent Form 4 insider trades."""
    _ensure_table()
    filings = _fetch_form4_filings(days_back=days_back)
    all_tx = []
    for filing in filings:
        all_tx.extend(_parse_filing(filing))
        time.sleep(0.05)
    _store_transactions(all_tx)
    return len(all_tx)


def get_insider_score(ticker: str, days: int = 30) -> float:
    """
    Insider signal score in [-1, 1] for ticker over last N days.

    Score logic:
      +1.0 for large open-market purchase (>$100k = conviction buy)
      +0.5 for small purchase
      -0.3 for sale (insiders sell for many reasons, weaker signal)
      Net score capped to [-1, 1], weighted by recency.

    Returns 0.0 if no data.
    """
    _ensure_table()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    conn = database.get_connection()
    try:
        rows = conn.execute("""
            SELECT transaction_code, shares, price, value_usd, trade_date
            FROM insider_trades
            WHERE ticker=? AND trade_date >= ?
            ORDER BY trade_date DESC
        """, (ticker.split(".")[0].upper(), cutoff)).fetchall()
    finally:
        conn.close()

    if not rows:
        return 0.0

    score = 0.0
    for row in rows:
        val = float(row["value_usd"] or 0)
        code = row["transaction_code"]
        if code in BULLISH_CODES:
            weight = 1.0 if val >= 100_000 else 0.5
            score += weight
        elif code in BEARISH_CODES:
            score -= 0.3

    return max(-1.0, min(1.0, score / max(len(rows), 1)))


def _ensure_table():
    conn = database.get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS insider_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                insider_name TEXT,
                transaction_code TEXT,
                shares REAL,
                price REAL,
                value_usd REAL,
                trade_date TEXT,
                is_buy INTEGER DEFAULT 0,
                fetched_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ticker, insider_name, trade_date, transaction_code, shares)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_insider_ticker ON insider_trades(ticker)")
        conn.commit()
    finally:
        conn.close()
