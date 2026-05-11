"""
Fetch real sector, industry, and fundamentals from yfinance for Tier 2 tickers.
Updates ticker_universe.sector and fundamentals table.
"""

import logging
import time
from datetime import datetime, timezone

import yfinance as yf

import database
from data.universe_manager import get_tickers_by_tier

logger = logging.getLogger(__name__)


def fetch_yfinance_fundamentals():
    """Fetch sector + fundamentals for all Tier 2 tickers via yfinance.info."""
    tickers = get_tickers_by_tier(2)
    logger.info("Fetching yfinance fundamentals for %d Tier 2 tickers", len(tickers))

    saved = 0
    conn = database.get_connection()
    try:
        for ticker in tickers:
            try:
                yf_ticker = yf.Ticker(ticker)
                info = {}

                # .info returns {} silently for some NSE tickers — retry once
                for attempt in range(2):
                    try:
                        info = yf_ticker.info or {}
                        if info.get("regularMarketPrice") or info.get("sector"):
                            break
                    except Exception:
                        pass
                    if attempt == 0:
                        time.sleep(1.0)

                # fast_info fallback for market cap when .info is empty
                mktcap = info.get("marketCap")
                if not mktcap:
                    try:
                        fi = yf_ticker.fast_info
                        mktcap = getattr(fi, "market_cap", None)
                    except Exception:
                        pass

                sector   = info.get("sector") or info.get("quoteType")
                industry = info.get("industry")
                pe       = info.get("trailingPE") or info.get("forwardPE")
                roe      = info.get("returnOnEquity")
                de       = info.get("debtToEquity")
                margin   = info.get("profitMargins")
                eps      = info.get("trailingEps")
                now      = datetime.now(timezone.utc).isoformat()

                # Update sector in ticker_universe
                if sector:
                    conn.execute("""
                        UPDATE ticker_universe SET sector=?, industry=?, market_cap=?
                        WHERE ticker=?
                    """, (sector, industry, mktcap, ticker))
                elif mktcap:
                    conn.execute(
                        "UPDATE ticker_universe SET market_cap=? WHERE ticker=?",
                        (mktcap, ticker)
                    )

                # Upsert fundamentals (save even if sparse — partial data beats nothing)
                if any(v is not None for v in [pe, eps, margin, roe, de, mktcap]):
                    conn.execute("""
                        INSERT INTO fundamentals
                            (ticker, pe_ratio, eps, profit_margin, roe, debt_to_equity, updated_at)
                        VALUES (?,?,?,?,?,?,?)
                        ON CONFLICT(ticker) DO UPDATE SET
                            pe_ratio=COALESCE(excluded.pe_ratio, pe_ratio),
                            eps=COALESCE(excluded.eps, eps),
                            profit_margin=COALESCE(excluded.profit_margin, profit_margin),
                            roe=COALESCE(excluded.roe, roe),
                            debt_to_equity=COALESCE(excluded.debt_to_equity, debt_to_equity),
                            updated_at=excluded.updated_at
                    """, (ticker, pe, eps, margin, roe, de, now))

                saved += 1
                if saved % 20 == 0:
                    conn.commit()
                    logger.info("Fundamentals: %d/%d done", saved, len(tickers))

            except Exception as exc:
                logger.debug("yfinance info failed for %s: %s", ticker, exc)

            time.sleep(0.3)  # gentle rate limit

        conn.commit()
        logger.info("yfinance fundamentals done: %d/%d tickers updated", saved, len(tickers))
    finally:
        conn.close()
