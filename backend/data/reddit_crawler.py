"""
Social sentiment crawler — replaces Reddit with free RSS sources:
- StockTwits RSS
- Google News RSS (per ticker)
- Moneycontrol RSS
- Economic Times RSS
- Finviz news (scrape)
No API keys needed. No rate limits.
"""

import hashlib
import json
import logging
import re
import time
from datetime import datetime, timezone

import feedparser
import requests

import database

logger = logging.getLogger(__name__)

_ticker_regex: re.Pattern | None = None

STATIC_FEEDS = [
    ("https://stocktwits.com/news/stocks/rss", "StockTwits"),
    ("https://economictimes.indiatimes.com/markets/stocks/rss.cms", "EconomicTimes"),
    ("https://www.moneycontrol.com/rss/marketsindia.xml", "Moneycontrol"),
    ("https://www.moneycontrol.com/rss/economy.xml", "Moneycontrol-Economy"),
    ("https://feeds.feedburner.com/ndtvprofit-latest", "NDTVProfit"),
    ("https://www.thehindubusinessline.com/markets/?service=rss", "HinduBusinessLine"),
]

HEADERS = {"User-Agent": "Mozilla/5.0 StockBot/1.0"}


def _build_ticker_regex() -> re.Pattern:
    global _ticker_regex
    conn = database.get_connection()
    try:
        rows = conn.execute("SELECT ticker FROM ticker_universe WHERE active=1").fetchall()
        symbols = [r["ticker"].split(".")[0] for r in rows if len(r["ticker"].split(".")[0]) >= 2]
        escaped = [re.escape(s) for s in symbols]
        _ticker_regex = re.compile(r"\b(" + "|".join(escaped) + r")\b")
        return _ticker_regex
    finally:
        conn.close()


def _extract_tickers(text: str) -> list[str]:
    if _ticker_regex is None:
        _build_ticker_regex()
    if not text:
        return []
    return list(set(_ticker_regex.findall(text)))


def _store_mention(ticker: str, source: str, text: str, created_at: str):
    conn = database.get_connection()
    try:
        conn.execute("""
            INSERT INTO social_mentions (ticker, source, text, created_at)
            VALUES (?,?,?,?)
        """, (ticker, source, text[:400], created_at))
        conn.commit()
    finally:
        conn.close()


def _crawl_static_feeds() -> int:
    count = 0
    for feed_url, source_name in STATIC_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                headline = getattr(entry, "title", "")
                summary = getattr(entry, "summary", "")
                published = getattr(entry, "published", datetime.now(timezone.utc).isoformat())
                text = headline + " " + summary
                tickers = _extract_tickers(text)
                for ticker in tickers:
                    _store_mention(ticker, source_name, headline, str(published))
                    count += 1
            time.sleep(0.3)
        except Exception as exc:
            logger.warning("%s feed failed: %s", source_name, exc)
    return count


def _crawl_google_news_per_ticker() -> int:
    """Fetch Google News RSS for each Tier 2 ticker."""
    conn = database.get_connection()
    try:
        rows = conn.execute(
            "SELECT ticker FROM ticker_universe WHERE active=1 AND tier=2"
        ).fetchall()
        tickers = [r["ticker"] for r in rows]
    finally:
        conn.close()

    count = 0
    for ticker in tickers:
        base = ticker.split(".")[0]
        url = f"https://news.google.com/rss/search?q={base}+stock&hl=en-IN&gl=IN&ceid=IN:en"
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:10]:
                headline = getattr(entry, "title", "")
                published = getattr(entry, "published", datetime.now(timezone.utc).isoformat())
                _store_mention(base, "GoogleNews", headline, str(published))
                count += 1
            time.sleep(0.5)
        except Exception as exc:
            logger.debug("Google News for %s failed: %s", ticker, exc)

    return count


def _crawl_finviz(tickers: list[str]) -> int:
    """Scrape Finviz news headlines for US tickers."""
    count = 0
    for ticker in tickers[:50]:  # limit to avoid hammering
        base = ticker.split(".")[0]
        url = f"https://finviz.com/quote.ashx?t={base}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                continue
            # Extract news headlines via simple regex (no BS4 needed)
            headlines = re.findall(r'class="news-link-left"[^>]*>([^<]+)<', resp.text)
            now = datetime.now(timezone.utc).isoformat()
            for h in headlines[:10]:
                _store_mention(base, "Finviz", h.strip(), now)
                count += 1
            time.sleep(1.0)  # be polite to Finviz
        except Exception as exc:
            logger.debug("Finviz %s failed: %s", ticker, exc)
    return count


def crawl():
    _build_ticker_regex()
    total = 0

    logger.info("Crawling static RSS feeds...")
    total += _crawl_static_feeds()

    logger.info("Crawling Google News per Tier 2 ticker...")
    total += _crawl_google_news_per_ticker()

    # Finviz only for US tickers
    conn = database.get_connection()
    try:
        us_rows = conn.execute("""
            SELECT ticker FROM ticker_universe
            WHERE active=1 AND tier=2 AND exchange IN ('NASDAQ','NYSE/AMEX')
        """).fetchall()
        us_tickers = [r["ticker"] for r in us_rows]
    finally:
        conn.close()

    logger.info("Crawling Finviz for %d US Tier 2 tickers...", len(us_tickers))
    total += _crawl_finviz(us_tickers)

    logger.info("Social crawl complete: %d new mentions", total)
