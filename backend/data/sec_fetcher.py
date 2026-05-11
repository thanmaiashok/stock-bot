"""
SEC EDGAR fundamentals fetcher. US tickers only. No API key needed.
"""

import json
import logging
import time
from datetime import datetime, timezone

import requests

import database

logger = logging.getLogger(__name__)

EDGAR_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
EDGAR_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
EDGAR_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

HEADERS = {
    "User-Agent": "StockBot/1.0 research@stockbot.local",
    "Accept": "application/json",
}

_cik_map: dict[str, int] = {}


def _load_cik_map():
    global _cik_map
    if _cik_map:
        return
    try:
        resp = requests.get(EDGAR_TICKERS_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        for entry in data.values():
            ticker = entry.get("ticker", "").upper()
            cik = int(entry.get("cik_str", 0))
            if ticker and cik:
                _cik_map[ticker] = cik
        logger.info("Loaded %d ticker→CIK mappings from SEC EDGAR", len(_cik_map))
    except Exception as exc:
        logger.error("Failed to load CIK map: %s", exc)


def _get_concept(facts: dict, taxonomy: str, concept: str) -> float | None:
    try:
        units = facts["facts"][taxonomy][concept]["units"]
        key = list(units.keys())[0]
        entries = units[key]
        # Get most recent annual (10-K) value
        annual = [e for e in entries if e.get("form") in ("10-K", "10-K/A") and "val" in e]
        if annual:
            annual.sort(key=lambda x: x.get("end", ""), reverse=True)
            return float(annual[0]["val"])
        # Fall back to any recent value
        entries.sort(key=lambda x: x.get("end", ""), reverse=True)
        return float(entries[0]["val"]) if entries else None
    except Exception:
        return None


def fetch_fundamentals_for_ticker(ticker: str) -> dict | None:
    _load_cik_map()
    # Strip exchange suffix
    base = ticker.split(".")[0].upper()
    cik = _cik_map.get(base)
    if not cik:
        logger.debug("No CIK for %s", ticker)
        return None

    try:
        resp = requests.get(EDGAR_FACTS_URL.format(cik=cik), headers=HEADERS, timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        facts = resp.json()
    except Exception as exc:
        logger.warning("EDGAR facts fetch failed for %s: %s", ticker, exc)
        return None

    net_income = _get_concept(facts, "us-gaap", "NetIncomeLoss")
    revenue = _get_concept(facts, "us-gaap", "Revenues") or \
              _get_concept(facts, "us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax")
    eps = _get_concept(facts, "us-gaap", "EarningsPerShareBasic")
    assets = _get_concept(facts, "us-gaap", "Assets")
    liabilities = _get_concept(facts, "us-gaap", "Liabilities")
    equity = _get_concept(facts, "us-gaap", "StockholdersEquity")

    profit_margin = (net_income / revenue) if net_income and revenue and revenue > 0 else None
    roe = (net_income / equity) if net_income and equity and equity > 0 else None
    debt_to_equity = (liabilities / equity) if liabilities and equity and equity > 0 else None

    return {
        "ticker": ticker,
        "eps": eps,
        "profit_margin": profit_margin,
        "roe": roe,
        "debt_to_equity": debt_to_equity,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def fetch_tier_fundamentals():
    """Fetch fundamentals for Tier 1+2 US tickers."""
    conn = database.get_connection()
    try:
        rows = conn.execute("""
            SELECT ticker FROM ticker_universe
            WHERE active=1 AND tier>=1 AND exchange IN ('NASDAQ','NYSE/AMEX')
        """).fetchall()
        tickers = [r["ticker"] for r in rows]
    finally:
        conn.close()

    logger.info("Fetching fundamentals for %d US tickers", len(tickers))
    saved = 0
    conn = database.get_connection()
    try:
        cur = conn.cursor()
        for ticker in tickers:
            data = fetch_fundamentals_for_ticker(ticker)
            if data:
                cur.execute("""
                    INSERT INTO fundamentals
                        (ticker, eps, profit_margin, roe, debt_to_equity, updated_at)
                    VALUES (?,?,?,?,?,?)
                    ON CONFLICT(ticker) DO UPDATE SET
                        eps=excluded.eps,
                        profit_margin=excluded.profit_margin,
                        roe=excluded.roe,
                        debt_to_equity=excluded.debt_to_equity,
                        updated_at=excluded.updated_at
                """, (
                    data["ticker"], data.get("eps"), data.get("profit_margin"),
                    data.get("roe"), data.get("debt_to_equity"), data["updated_at"],
                ))
                saved += 1
            time.sleep(0.1)  # EDGAR rate limit: 10 req/sec
            if saved % 50 == 0:
                conn.commit()
                logger.debug("Fundamentals: saved %d/%d", saved, len(tickers))
        conn.commit()
        logger.info("Fundamentals fetch complete: %d/%d saved", saved, len(tickers))
    finally:
        conn.close()
