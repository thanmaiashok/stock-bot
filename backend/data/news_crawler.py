"""
RSS news crawler.
- Extracts stock ticker mentions from universe (regex + company name map).
- Extracts futures instrument mentions via keyword map.
- Scores each headline with VADER sentiment (-1 to +1).
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
from config import RSS_FEEDS

logger = logging.getLogger(__name__)

_ticker_regex: re.Pattern | None = None
_ticker_set: set[str] = set()
_name_to_ticker: dict[str, str] = {}   # "Apple" → "AAPL"

# Keyword → futures symbol map.  Keys are lowercase phrases/words.
# Each symbol may appear under multiple keywords.
FUTURES_KEYWORD_MAP: dict[str, list[str]] = {
    # Energy
    "crude oil": ["CL=F", "BZ=F"], "wti": ["CL=F"], "opec": ["CL=F", "BZ=F"],
    "brent": ["BZ=F"], "oil barrel": ["CL=F"], "petroleum": ["CL=F"],
    "natural gas": ["NG=F"], "lng": ["NG=F"], "gas prices": ["NG=F"],
    "gasoline": ["RB=F"], "rbob": ["RB=F"], "fuel prices": ["RB=F", "HO=F"],
    "heating oil": ["HO=F"],
    # Metals
    "gold prices": ["GC=F"], "gold rally": ["GC=F"], "bullion": ["GC=F"],
    "safe haven": ["GC=F"], "inflation hedge": ["GC=F"], "gold futures": ["GC=F"],
    "silver prices": ["SI=F"], "silver futures": ["SI=F"],
    "copper": ["HG=F"], "industrial metals": ["HG=F", "SI=F"],
    "platinum": ["PL=F"], "palladium": ["PA=F"], "catalytic converter": ["PA=F"],
    # Agriculture
    "corn prices": ["ZC=F"], "corn futures": ["ZC=F"], "ethanol": ["ZC=F"],
    "wheat prices": ["ZW=F", "KE=F"], "grain prices": ["ZW=F", "ZC=F", "ZS=F"],
    "food prices": ["ZW=F", "ZC=F", "ZS=F"], "wheat futures": ["ZW=F"],
    "soybean": ["ZS=F"], "soy prices": ["ZS=F"],
    "oats": ["ZO=F"],
    "sugar prices": ["SB=F"], "sugar futures": ["SB=F"],
    "coffee prices": ["KC=F"], "coffee futures": ["KC=F"],
    "cotton prices": ["CT=F"], "cotton futures": ["CT=F"],
    "cocoa": ["CC=F"], "chocolate prices": ["CC=F"],
    # Indices
    "s&p 500": ["ES=F"], "s&p500": ["ES=F"], "spx": ["ES=F"],
    "stock market rally": ["ES=F", "NQ=F", "YM=F"],
    "wall street": ["ES=F", "YM=F"], "equities rally": ["ES=F", "NQ=F"],
    "nasdaq": ["NQ=F"], "tech stocks": ["NQ=F"], "technology rally": ["NQ=F"],
    "dow jones": ["YM=F"], "djia": ["YM=F"], "dow": ["YM=F"],
    "russell 2000": ["RTY=F"], "small cap": ["RTY=F"], "small-cap": ["RTY=F"],
    "nikkei": ["NKD=F"], "japanese stocks": ["NKD=F"],
    # Bonds / Rates
    "treasury": ["ZB=F", "ZN=F"], "t-bond": ["ZB=F"], "government bond": ["ZB=F", "ZN=F"],
    "bond yield": ["ZN=F", "ZB=F"], "10-year yield": ["ZN=F"], "10y yield": ["ZN=F"],
    "federal reserve": ["ZN=F", "ZB=F"], "fed rate": ["ZN=F"], "interest rate": ["ZN=F", "ZB=F"],
    # FX
    "euro": ["EURUSD=X"], "ecb": ["EURUSD=X"], "european central bank": ["EURUSD=X"],
    "british pound": ["GBPUSD=X"], "sterling": ["GBPUSD=X"], "bank of england": ["GBPUSD=X"],
    "japanese yen": ["USDJPY=X"], "bank of japan": ["USDJPY=X"], "boj": ["USDJPY=X"],
    "australian dollar": ["AUDUSD=X"], "rba": ["AUDUSD=X"],
    "canadian dollar": ["USDCAD=X"], "loonie": ["USDCAD=X"],
    "swiss franc": ["USDCHF=X"], "snb": ["USDCHF=X"],
    "rupee": ["USDINR=X"], "rbi": ["USDINR=X"], "india gdp": ["USDINR=X"],
    # Crypto
    "bitcoin": ["BTC-USD"], "btc": ["BTC-USD"], "crypto rally": ["BTC-USD", "ETH-USD"],
    "ethereum": ["ETH-USD"], "defi": ["ETH-USD"], "smart contract": ["ETH-USD"],
    "binance": ["BNB-USD"], "solana": ["SOL-USD"], "ripple": ["XRP-USD"],
    "xrp": ["XRP-USD"], "cardano": ["ADA-USD"],
}

# Pre-compiled: longest phrases first to avoid partial matches
_FUTURES_RE: re.Pattern | None = None


def _get_futures_re() -> re.Pattern:
    global _FUTURES_RE
    if _FUTURES_RE is None:
        terms = sorted(FUTURES_KEYWORD_MAP.keys(), key=len, reverse=True)
        pattern = "|".join(re.escape(t) for t in terms)
        _FUTURES_RE = re.compile(pattern, re.IGNORECASE)
    return _FUTURES_RE


def _extract_futures_mentions(text: str) -> list[str]:
    if not text:
        return []
    found: set[str] = set()
    for match in _get_futures_re().finditer(text.lower()):
        for sym in FUTURES_KEYWORD_MAP.get(match.group(), []):
            found.add(sym)
    return sorted(found)


def _score_sentiment(text: str) -> float:
    """VADER compound score: -1 (very negative) to +1 (very positive)."""
    try:
        from data.sentiment_scorer import _get_vader
        sid = _get_vader()
        return round(float(sid.polarity_scores(text)["compound"]), 4)
    except Exception:
        return 0.0


def _build_ticker_regex():
    global _ticker_regex, _ticker_set, _name_to_ticker
    conn = database.get_connection()
    try:
        rows = conn.execute(
            "SELECT ticker, name FROM ticker_universe WHERE active=1"
        ).fetchall()
        raw = [r["ticker"].split(".")[0] for r in rows]
        _ticker_set = set(raw)

        name_map = {}
        for r in rows:
            base = r["ticker"].split(".")[0]
            name = r["name"] or ""
            short = re.sub(
                r'\s+(Inc\.?|Corp\.?|Ltd\.?|LLC|PLC|NV|SE|AG|SA|Limited|Holdings?|Group|Co\.?|Class [AB].*|Common Stock.*|Ordinary Shares.*)$',
                '', name, flags=re.IGNORECASE
            ).strip()
            if short and len(short) >= 4 and short.upper() != base:
                name_map[short] = base
        _name_to_ticker = name_map

        ticker_terms = [re.escape(t) for t in raw if len(t) >= 2]
        name_terms   = [re.escape(n) for n in name_map.keys() if len(n) >= 4]
        all_terms    = sorted(set(ticker_terms + name_terms), key=len, reverse=True)
        pattern = r"\b(" + "|".join(all_terms) + r")\b"
        _ticker_regex = re.compile(pattern, re.IGNORECASE)
        logger.info("Built mention regex: %d tickers + %d company names", len(ticker_terms), len(name_terms))
    finally:
        conn.close()


def _extract_mentions(text: str) -> list[str]:
    if _ticker_regex is None:
        _build_ticker_regex()
    if not text:
        return []
    matches = _ticker_regex.findall(text)
    resolved = set()
    for m in matches:
        m_upper = m.upper()
        if m_upper in _ticker_set:
            resolved.add(m_upper)
        elif m in _name_to_ticker:
            resolved.add(_name_to_ticker[m])
        elif m.title() in _name_to_ticker:
            resolved.add(_name_to_ticker[m.title()])
    return list(resolved)


def crawl():
    global _ticker_regex
    _build_ticker_regex()

    conn = database.get_connection()
    new_count = 0
    hot_tickers: set[str] = set()
    try:
        cur = conn.cursor()
        for feed_url in RSS_FEEDS:
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries:
                    headline = getattr(entry, "title", "")
                    url      = getattr(entry, "link", "")
                    published = getattr(entry, "published", datetime.now(timezone.utc).isoformat())
                    summary  = getattr(entry, "summary", "")

                    full_text    = headline + " " + summary
                    url_hash     = hashlib.md5(url.encode()).hexdigest()
                    mentions     = _extract_mentions(full_text)
                    fut_mentions = _extract_futures_mentions(full_text)
                    sentiment    = _score_sentiment(headline)

                    try:
                        cur.execute("""
                            INSERT INTO news_articles
                                (url_hash, headline, url, source, published_at,
                                 ticker_mentions, futures_mentions, sentiment_score, sentiment_done)
                            VALUES (?,?,?,?,?,?,?,?,1)
                        """, (
                            url_hash, headline, url,
                            feed.feed.get("title", feed_url),
                            str(published),
                            json.dumps(mentions),
                            json.dumps(fut_mentions),
                            sentiment,
                        ))
                        new_count += 1
                        hot_tickers.update(mentions)
                    except Exception:
                        pass  # duplicate url_hash — skip
            except Exception as exc:
                logger.warning("RSS feed %s failed: %s", feed_url, exc)
            time.sleep(0.2)
        conn.commit()
        logger.info("News crawl: %d new articles", new_count)

        if new_count > 0 and hot_tickers:
            tier2 = {r["ticker"].split(".")[0] for r in conn.execute(
                "SELECT ticker FROM ticker_universe WHERE active=1 AND tier>=2"
            ).fetchall()}
            hot_tier2 = [t for t in hot_tickers if t in tier2]
            if hot_tier2:
                logger.info("News-triggered fetch for %d hot tickers: %s", len(hot_tier2), hot_tier2[:5])
                from data.market_fetcher import fetch_tickers_now
                fetch_tickers_now(hot_tier2)
    finally:
        conn.close()
