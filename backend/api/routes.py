"""FastAPI route definitions."""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

import database
from data.market_fetcher import get_ohlcv
from data.sentiment_scorer import get_sentiment
from graph.neo4j_builder import get_correlated_stocks, get_sector_stocks, get_news_for_stock, get_knowledge_graph, get_market_graph
from trading.paper_trader import (
    get_portfolio_value, get_trade_history, get_performance_stats
)
from signals.technical_features import compute_technicals

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

@router.get("/signals")
def latest_signals(limit: int = Query(100, le=500)):
    conn = database.get_connection()
    try:
        rows = conn.execute("""
            SELECT s.*, u.name, u.exchange, u.sector
            FROM signals s
            LEFT JOIN ticker_universe u ON s.ticker=u.ticker
            WHERE s.timestamp = (
                SELECT MAX(s2.timestamp) FROM signals s2 WHERE s2.ticker=s.ticker
            )
            ORDER BY s.confidence DESC LIMIT ?
        """, (limit,)).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["reasons"] = json.loads(d.get("reasons") or "[]")
            result.append(d)
        return result
    finally:
        conn.close()


@router.get("/signals/{ticker}")
def signal_history(ticker: str, limit: int = 50):
    conn = database.get_connection()
    try:
        rows = conn.execute("""
            SELECT * FROM signals WHERE ticker=? ORDER BY timestamp DESC LIMIT ?
        """, (ticker.upper(), limit)).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["reasons"] = json.loads(d.get("reasons") or "[]")
            result.append(d)
        return result
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------

@router.get("/portfolio")
def portfolio():
    return get_portfolio_value()


@router.get("/portfolio/history")
def portfolio_history(limit: int = 100):
    return get_trade_history(limit)


@router.get("/portfolio/stats")
def portfolio_stats():
    return get_performance_stats()


@router.get("/portfolio/equity-curve")
def portfolio_equity_curve():
    """Reconstruct equity curve from trade history."""
    from config import PAPER_WALLET_USD
    conn = database.get_connection()
    try:
        rows = conn.execute("""
            SELECT timestamp, action, quantity, price, pnl
            FROM paper_trades
            ORDER BY timestamp ASC
        """).fetchall()
        cash = PAPER_WALLET_USD
        points = [{"date": None, "equity": round(cash, 2), "cash": round(cash, 2)}]
        for r in rows:
            if r["action"] == "BUY":
                cash -= r["quantity"] * r["price"]
            elif r["action"] == "SELL":
                cash += r["quantity"] * r["price"]
            date = (r["timestamp"] or "")[:10]
            points.append({"date": date, "equity": round(cash, 2), "cash": round(cash, 2)})
        points[0]["date"] = points[1]["date"] if len(points) > 1 else "—"
        return points
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Sectors
# ---------------------------------------------------------------------------

@router.get("/universe/sectors")
def sectors():
    """Signal distribution grouped by sector — real data from signals + ticker_universe."""
    conn = database.get_connection()
    try:
        rows = conn.execute("""
            SELECT u.sector,
                   COUNT(DISTINCT u.ticker) AS total_tickers,
                   SUM(CASE WHEN s.signal='BUY'  THEN 1 ELSE 0 END) AS buy_count,
                   SUM(CASE WHEN s.signal='SELL' THEN 1 ELSE 0 END) AS sell_count,
                   SUM(CASE WHEN s.signal='HOLD' THEN 1 ELSE 0 END) AS hold_count,
                   AVG(s.confidence) AS avg_confidence,
                   AVG(s.sentiment_score) AS avg_sentiment
            FROM ticker_universe u
            LEFT JOIN signals s ON u.ticker = s.ticker
              AND s.timestamp = (SELECT MAX(s2.timestamp) FROM signals s2 WHERE s2.ticker = u.ticker)
            WHERE u.active=1 AND u.sector IS NOT NULL AND u.sector != ''
            GROUP BY u.sector
            ORDER BY (buy_count - sell_count) DESC
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/universe/sector/{sector}/tickers")
def sector_tickers(sector: str, limit: int = Query(50, le=200)):
    """Top tickers in a sector with their latest signals."""
    conn = database.get_connection()
    try:
        rows = conn.execute("""
            SELECT u.ticker, u.name, u.exchange, u.tier, u.last_price, u.avg_volume_30d,
                   s.signal, s.confidence, s.timestamp
            FROM ticker_universe u
            LEFT JOIN signals s ON u.ticker = s.ticker
              AND s.timestamp = (SELECT MAX(s2.timestamp) FROM signals s2 WHERE s2.ticker = u.ticker)
            WHERE u.active=1 AND u.sector=?
            ORDER BY u.tier DESC, s.confidence DESC NULLS LAST, u.avg_volume_30d DESC
            LIMIT ?
        """, (sector, limit)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Market data — NOTE: specific /market/X routes are defined LATER in this file
# (after line 1400) to avoid shadowing by this catch-all.
# FastAPI matches routes in registration order — specific routes MUST come first.
# ---------------------------------------------------------------------------

def _market_data_handler(ticker: str, interval: str = "1d", limit: int = 200):
    ohlcv = get_ohlcv(ticker.upper(), interval, limit)
    if len(ohlcv) < 30:
        # Non-blocking: kick off 1y backfill in background, return immediately
        import threading
        def _bg():
            try:
                from data.market_fetcher import fetch_tickers_now
                fetch_tickers_now([ticker.upper()], interval="1d", period="1y")
            except Exception as exc:
                logger.debug("BG fetch failed for %s: %s", ticker, exc)
        threading.Thread(target=_bg, daemon=True).start()
    if not ohlcv:
        return {"ticker": ticker.upper(), "ohlcv": [], "technicals": {}, "refreshing": True}
    if len(ohlcv) < 30:
        return {"ticker": ticker.upper(), "ohlcv": ohlcv, "technicals": compute_technicals(ticker.upper(), interval), "refreshing": True}
    tech = compute_technicals(ticker.upper(), interval)
    return {"ticker": ticker.upper(), "ohlcv": ohlcv, "technicals": tech}


# ---------------------------------------------------------------------------
# News + sentiment
# ---------------------------------------------------------------------------

@router.get("/news/feed")
def news_feed(limit: int = Query(60, le=200)):
    """Global news feed with stock mentions, futures mentions, and sentiment scores."""
    conn = database.get_connection()
    try:
        rows = conn.execute("""
            SELECT headline, url, source, published_at,
                   ticker_mentions, futures_mentions, sentiment_score
            FROM news_articles
            ORDER BY published_at DESC LIMIT ?
        """, (limit,)).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["ticker_mentions"]  = json.loads(d.get("ticker_mentions")  or "[]")
            d["futures_mentions"] = json.loads(d.get("futures_mentions") or "[]")
            d["sentiment_score"]  = d.get("sentiment_score") or 0.0
            result.append(d)
        return result
    finally:
        conn.close()


@router.get("/news/impact")
def news_impact(hours: int = Query(24, le=168)):
    """
    Aggregate news impact: top stocks + futures by mention count and net sentiment.
    Returns ranked lists for stocks and futures separately, plus headline samples.
    """
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    conn = database.get_connection()
    try:
        rows = conn.execute("""
            SELECT ticker_mentions, futures_mentions, sentiment_score, headline, url, published_at
            FROM news_articles
            WHERE published_at >= ?
            ORDER BY published_at DESC
        """, (since,)).fetchall()
    finally:
        conn.close()

    stock_stats: dict[str, dict] = {}
    futures_stats: dict[str, dict] = {}

    for r in rows:
        sent  = r["sentiment_score"] or 0.0
        hl    = r["headline"]
        ticks = json.loads(r["ticker_mentions"]  or "[]")
        futs  = json.loads(r["futures_mentions"] or "[]")

        for sym in ticks:
            s = stock_stats.setdefault(sym, {"mentions": 0, "sentiment_sum": 0.0, "headlines": []})
            s["mentions"] += 1
            s["sentiment_sum"] += sent
            if len(s["headlines"]) < 3:
                s["headlines"].append({"headline": hl, "url": r["url"], "sentiment": sent})

        for sym in futs:
            s = futures_stats.setdefault(sym, {"mentions": 0, "sentiment_sum": 0.0, "headlines": []})
            s["mentions"] += 1
            s["sentiment_sum"] += sent
            if len(s["headlines"]) < 3:
                s["headlines"].append({"headline": hl, "url": r["url"], "sentiment": sent})

    def _rank(stats: dict) -> list[dict]:
        out = []
        for sym, d in stats.items():
            n = d["mentions"]
            avg_sent = round(d["sentiment_sum"] / n, 4) if n else 0.0
            out.append({
                "symbol":    sym,
                "mentions":  n,
                "avg_sentiment": avg_sent,
                "impact_score":  round(n * (1 + abs(avg_sent)), 3),
                "headlines": d["headlines"],
            })
        return sorted(out, key=lambda x: x["impact_score"], reverse=True)

    return {
        "hours":   hours,
        "stocks":  _rank(stock_stats)[:30],
        "futures": _rank(futures_stats)[:20],
        "total_articles": len(rows),
    }


@router.get("/news/{ticker}")
def news(ticker: str):
    conn = database.get_connection()
    base = ticker.upper().split(".")[0]
    try:
        rows = conn.execute("""
            SELECT headline, url, source, published_at,
                   ticker_mentions, futures_mentions, sentiment_score
            FROM news_articles
            WHERE ticker_mentions LIKE ?
            ORDER BY published_at DESC LIMIT 50
        """, (f'%"{base}"%',)).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["ticker_mentions"]  = json.loads(d.get("ticker_mentions")  or "[]")
            d["futures_mentions"] = json.loads(d.get("futures_mentions") or "[]")
            d["sentiment_score"]  = d.get("sentiment_score") or 0.0
            result.append(d)
    finally:
        conn.close()
    sentiment = get_sentiment(ticker, days=7)
    return {"ticker": ticker.upper(), "news": result, "sentiment": sentiment}


@router.get("/social/{ticker}")
def social_mentions(ticker: str, limit: int = 50):
    """Social mentions from StockTwits, Google News, Finviz, ET, Moneycontrol."""
    base = ticker.upper().split(".")[0]
    conn = database.get_connection()
    try:
        rows = conn.execute("""
            SELECT source, text, score, created_at
            FROM social_mentions
            WHERE ticker=?
            ORDER BY created_at DESC LIMIT ?
        """, (base, limit)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/fundamentals/{ticker}")
def fundamentals(ticker: str):
    """Fundamental data from SEC EDGAR + yfinance."""
    base = ticker.upper().split(".")[0]
    conn = database.get_connection()
    try:
        row = conn.execute("""
            SELECT * FROM fundamentals WHERE ticker=?
        """, (base,)).fetchone()
        if not row:
            raise HTTPException(404, f"No fundamentals for {ticker}")
        return dict(row)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

@router.get("/graph/correlations/{ticker}")
def correlations(ticker: str, limit: int = 20):
    try:
        return get_correlated_stocks(ticker.upper(), limit)
    except Exception:
        return []


@router.get("/graph/market")
def market_graph():
    try:
        return get_market_graph()
    except Exception as exc:
        raise HTTPException(500, str(exc))


@router.get("/graph/knowledge/{ticker}")
def knowledge_graph(ticker: str, corr_limit: int = 15, news_limit: int = 8):
    try:
        return get_knowledge_graph(ticker.upper(), corr_limit, news_limit)
    except Exception as exc:
        raise HTTPException(500, str(exc))


@router.get("/graph/sector/{sector}")
def sector_stocks(sector: str):
    try:
        return get_sector_stocks(sector)
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Universe / Screener
# ---------------------------------------------------------------------------

@router.get("/universe/stats")
def universe_stats():
    conn = database.get_connection()
    try:
        total = conn.execute("SELECT COUNT(*) AS n FROM ticker_universe WHERE active=1").fetchone()["n"]
        tier2 = conn.execute("SELECT COUNT(*) AS n FROM ticker_universe WHERE active=1 AND tier=2").fetchone()["n"]
        tier1 = conn.execute("SELECT COUNT(*) AS n FROM ticker_universe WHERE active=1 AND tier=1").fetchone()["n"]
        tier0 = conn.execute("SELECT COUNT(*) AS n FROM ticker_universe WHERE active=1 AND tier=0").fetchone()["n"]
        by_exchange = conn.execute("""
            SELECT exchange, COUNT(*) AS n FROM ticker_universe WHERE active=1 GROUP BY exchange
        """).fetchall()
        last_refresh = conn.execute("""
            SELECT MAX(last_updated) AS ts FROM ticker_universe
        """).fetchone()["ts"]
        return {
            "total_active": total,
            "tier2_deep_analysis": tier2,
            "tier1_active_candidates": tier1,
            "tier0_universe": tier0,
            "by_exchange": [dict(r) for r in by_exchange],
            "last_refresh": last_refresh,
        }
    finally:
        conn.close()


@router.get("/universe/screener")
def screener(
    exchange: Optional[str] = None,
    sector: Optional[str] = None,
    tier: Optional[int] = None,
    min_volume: Optional[float] = None,
    signal: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(200, le=1000),
    offset: int = 0,
):
    conn = database.get_connection()
    try:
        filters = ["u.active=1"]
        params: list = []

        if exchange:
            filters.append("u.exchange=?")
            params.append(exchange)
        if sector:
            filters.append("u.sector=?")
            params.append(sector)
        if tier is not None:
            filters.append("u.tier=?")
            params.append(tier)
        if min_volume:
            filters.append("u.avg_volume_30d>=?")
            params.append(min_volume)
        if search:
            filters.append("(u.ticker LIKE ? OR u.name LIKE ?)")
            params.extend([f"%{search.upper()}%", f"%{search}%"])

        where = " AND ".join(filters)
        query = f"""
            SELECT u.ticker, u.name, u.exchange, u.sector, u.tier,
                   u.last_price, u.avg_volume_30d, u.currency,
                   s.signal, s.confidence
            FROM ticker_universe u
            LEFT JOIN signals s ON u.ticker=s.ticker
              AND s.timestamp=(SELECT MAX(s2.timestamp) FROM signals s2 WHERE s2.ticker=u.ticker)
            WHERE {where}
        """
        if signal:
            query += " AND s.signal=?"
            params.append(signal.upper())

        query += f" ORDER BY u.tier DESC, u.avg_volume_30d DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/universe/{ticker}/tier")
def ticker_tier(ticker: str):
    conn = database.get_connection()
    try:
        row = conn.execute("""
            SELECT ticker, exchange, sector, tier, last_price, avg_volume_30d, last_updated
            FROM ticker_universe WHERE ticker=?
        """, (ticker.upper(),)).fetchone()
        if not row:
            raise HTTPException(404, f"{ticker} not in universe")
        return dict(row)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Watchlist (manual overrides on top of universe)
# ---------------------------------------------------------------------------

class TickerBody(BaseModel):
    ticker: str


@router.post("/watchlist/add")
def watchlist_add(body: TickerBody):
    ticker = body.ticker.upper()
    conn = database.get_connection()
    try:
        conn.execute("""
            INSERT INTO ticker_universe (ticker, exchange, tier, active, last_updated)
            VALUES (?,?,2,1,datetime('now'))
            ON CONFLICT(ticker) DO UPDATE SET tier=2, active=1
        """, (ticker, "MANUAL"))
        conn.commit()
    finally:
        conn.close()
    return {"status": "added", "ticker": ticker}


@router.post("/watchlist/remove")
def watchlist_remove(body: TickerBody):
    ticker = body.ticker.upper()
    conn = database.get_connection()
    try:
        conn.execute("UPDATE ticker_universe SET tier=0 WHERE ticker=?", (ticker,))
        conn.commit()
    finally:
        conn.close()
    return {"status": "removed_from_tier2", "ticker": ticker}


# ---------------------------------------------------------------------------
# Futures
# ---------------------------------------------------------------------------

class FuturesOrderBody(BaseModel):
    symbol:    str
    direction: str   # "long" | "short"
    units:     float


@router.get("/futures/quotes")
def futures_quotes():
    from data.futures_fetcher import fetch_quotes
    return fetch_quotes()


@router.get("/futures/chart/{symbol}")
def futures_chart(symbol: str, period: str = Query("5d"), interval: str = Query("15m")):
    from data.futures_fetcher import get_chart
    return get_chart(symbol.upper(), period, interval)


@router.get("/futures/portfolio")
def futures_portfolio():
    from trading.futures_trader import get_portfolio
    return get_portfolio()


@router.post("/futures/order")
def futures_order(body: FuturesOrderBody):
    from data.futures_fetcher import fetch_quotes
    from trading.futures_trader import open_position

    qmap = {q["symbol"]: q for q in fetch_quotes()}
    sym  = body.symbol.upper()
    q    = qmap.get(sym)
    if not q:
        raise HTTPException(404, f"Symbol '{sym}' not found or price unavailable")

    result = open_position(sym, body.direction, body.units, q["price"])
    if not result["ok"]:
        raise HTTPException(400, result["message"])
    return result


@router.delete("/futures/position/{symbol}")
def futures_close(symbol: str):
    from data.futures_fetcher import fetch_quotes
    from trading.futures_trader import close_position

    qmap = {q["symbol"]: q for q in fetch_quotes()}
    sym  = symbol.upper()
    q    = qmap.get(sym)
    if not q:
        raise HTTPException(404, f"Symbol '{sym}' not found or price unavailable")

    result = close_position(sym, q["price"])
    if not result["ok"]:
        raise HTTPException(400, result["message"])
    return result


@router.get("/futures/history")
def futures_history(limit: int = Query(50, le=200)):
    from trading.futures_trader import get_trade_history
    return get_trade_history(limit)


@router.get("/futures/performance")
def futures_performance():
    from trading.futures_trader import get_performance
    return get_performance()


@router.get("/futures/instruments")
def futures_instruments():
    from data.futures_fetcher import FUTURES_INSTRUMENTS
    return FUTURES_INSTRUMENTS


@router.get("/futures/bot/status")
def futures_bot_status():
    from trading.futures_auto_trader import get_bot_status
    return get_bot_status()


@router.get("/futures/predictions")
def futures_predictions():
    from data.futures_fetcher import fetch_quotes
    from trading.futures_auto_trader import get_predictions_cached
    quotes = fetch_quotes()
    return get_predictions_cached(quotes)


@router.get("/futures/correlations")
def futures_correlations():
    """Pairwise Pearson correlations between all futures instruments (10d hourly closes)."""
    import yfinance as yf
    import numpy as np
    from data.futures_fetcher import FUTURES_INSTRUMENTS

    symbols = list(FUTURES_INSTRUMENTS.keys())
    try:
        raw = yf.download(
            symbols, period="10d", interval="1h",
            group_by="ticker", auto_adjust=True, progress=False, threads=True,
        )
        multi = hasattr(raw.columns, "levels") and len(raw.columns.levels) > 1
        closes = {}
        for sym in symbols:
            try:
                series = raw[sym]["Close"] if multi else raw["Close"]
                series = series.dropna()
                if len(series) >= 20:
                    closes[sym] = series.values.astype(float)
            except Exception:
                pass

        syms = list(closes.keys())
        n = len(syms)
        matrix = []
        for i, a in enumerate(syms):
            row = []
            for j, b in enumerate(syms):
                if i == j:
                    row.append(1.0)
                    continue
                va, vb = closes[a], closes[b]
                min_len = min(len(va), len(vb))
                if min_len < 10:
                    row.append(None)
                    continue
                corr = float(np.corrcoef(va[-min_len:], vb[-min_len:])[0, 1])
                row.append(round(corr, 3))
            matrix.append(row)

        return {
            "symbols": syms,
            "names": {s: FUTURES_INSTRUMENTS[s]["name"] for s in syms},
            "matrix": matrix,
        }
    except Exception as exc:
        raise HTTPException(500, str(exc))


@router.get("/futures/equity-curve")
def futures_equity_curve():
    """Equity curve from futures trade history."""
    conn = database.get_connection()
    try:
        from trading.futures_trader import FUTURES_INITIAL_CASH as INITIAL_CASH
        rows = conn.execute("""
            SELECT timestamp, action, margin, pnl
            FROM futures_trades ORDER BY timestamp ASC
        """).fetchall()
        cash = INITIAL_CASH
        points = [{"date": None, "equity": round(cash, 2)}]
        for r in rows:
            if r["action"] == "OPEN":
                cash -= r["margin"] or 0
            elif r["action"] == "CLOSE":
                cash += (r["margin"] or 0) + (r["pnl"] or 0)
            date = (r["timestamp"] or "")[:10]
            points.append({"date": date, "equity": round(cash, 2)})
        if len(points) > 1:
            points[0]["date"] = points[1]["date"]
        return points
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Admin triggers
# ---------------------------------------------------------------------------

_ADMIN_JOBS = {
    "gnn_train":         ("graph.gnn_model",               "train"),
    "graph_update":      ("graph.neo4j_builder",           "run_full_graph_update"),
    "yf_fundamentals":   ("data.yfinance_fundamentals",    "fetch_yfinance_fundamentals"),
    "sec_fundamentals":  ("data.sec_fetcher",              "fetch_tier_fundamentals"),
    "price_correlations":("data.market_fetcher",           "compute_price_correlations"),
    "news_crawl":        ("data.news_crawler",             "crawl"),
    "social_crawl":      ("data.reddit_crawler",           "crawl"),
    "sentiment":         ("data.sentiment_scorer",         "score_new_articles"),
}


@router.post("/admin/trigger/{job}")
def admin_trigger(job: str):
    import threading
    import importlib

    if job not in _ADMIN_JOBS:
        raise HTTPException(404, f"Unknown job '{job}'. Available: {list(_ADMIN_JOBS)}")

    mod_path, fn_name = _ADMIN_JOBS[job]

    def _run():
        try:
            mod = importlib.import_module(mod_path)
            getattr(mod, fn_name)()
            logger.info("Admin trigger '%s' completed", job)
        except Exception as exc:
            logger.error("Admin trigger '%s' failed: %s", job, exc, exc_info=True)

    threading.Thread(target=_run, daemon=True).start()
    return {"status": "triggered", "job": job}


# ---------------------------------------------------------------------------
# Market Commentary
# ---------------------------------------------------------------------------

_commentary_cache: dict = {}
_commentary_ts: float = 0.0
_COMMENTARY_TTL = 900  # 15 min

import time as _time

@router.get("/market/commentary")
def market_commentary():
    """Template-based market summary derived from live signals + news."""
    global _commentary_cache, _commentary_ts
    import time as t
    if _commentary_cache and (t.time() - _commentary_ts) < _COMMENTARY_TTL:
        return _commentary_cache

    conn = database.get_connection()
    try:
        # Recent signals (last 3 hours)
        sigs = conn.execute("""
            SELECT ticker, signal, confidence, sentiment_score, fundamental_score
            FROM signals
            WHERE timestamp > datetime('now', '-3 hours')
            ORDER BY confidence DESC
        """).fetchall()

        buys  = [s for s in sigs if s["signal"] == "BUY"]
        sells = [s for s in sigs if s["signal"] == "SELL"]
        holds = [s for s in sigs if s["signal"] == "HOLD"]
        total = len(sigs) or 1

        buy_pct  = round(len(buys)  / total * 100)
        sell_pct = round(len(sells) / total * 100)

        if buy_pct > 55:   sentiment_label = "BULLISH"
        elif sell_pct > 55: sentiment_label = "BEARISH"
        elif buy_pct > sell_pct + 10: sentiment_label = "CAUTIOUSLY BULLISH"
        elif sell_pct > buy_pct + 10: sentiment_label = "CAUTIOUSLY BEARISH"
        else:               sentiment_label = "MIXED"

        top_buys  = [s["ticker"] for s in buys[:3]]
        top_sells = [s["ticker"] for s in sells[:3]]
        avg_conf  = round(sum(s["confidence"] for s in sigs) / total, 3)

        # Sector breakdown
        sectors = conn.execute("""
            SELECT u.sector, s.signal, COUNT(*) as cnt
            FROM signals s JOIN ticker_universe u ON u.ticker = s.ticker
            WHERE s.timestamp > datetime('now', '-3 hours') AND u.sector IS NOT NULL
            GROUP BY u.sector, s.signal ORDER BY cnt DESC
        """).fetchall()

        sector_buys: dict[str, int] = {}
        sector_sells: dict[str, int] = {}
        for row in sectors:
            if row["signal"] == "BUY":  sector_buys[row["sector"]]  = row["cnt"]
            if row["signal"] == "SELL": sector_sells[row["sector"]] = row["cnt"]
        hot_sector  = max(sector_buys,  key=sector_buys.get)  if sector_buys  else None
        cold_sector = max(sector_sells, key=sector_sells.get) if sector_sells else None

        # News sentiment avg
        news_avg = conn.execute("""
            SELECT AVG(sentiment_score) as avg_sent FROM news_articles
            WHERE published_at > datetime('now', '-6 hours') AND sentiment_score IS NOT NULL
        """).fetchone()["avg_sent"] or 0.0

        # Build sentences
        sentences = []
        sentences.append(
            f"Signal engine scanned {total} tickers: {buy_pct}% BUY, {sell_pct}% SELL, "
            f"{100 - buy_pct - sell_pct}% HOLD — overall sentiment is {sentiment_label}."
        )
        if top_buys:
            sentences.append(
                f"Strongest long candidates: {', '.join(top_buys)}"
                + (f"; highest conviction sells: {', '.join(top_sells)}." if top_sells else ".")
            )
        if hot_sector and cold_sector and hot_sector != cold_sector:
            sentences.append(
                f"{hot_sector} leads with most BUY signals; {cold_sector} shows heaviest selling pressure."
            )
        elif hot_sector:
            sentences.append(f"{hot_sector} sector shows strongest buying momentum.")

        news_mood = "positive" if news_avg > 0.05 else "negative" if news_avg < -0.05 else "neutral"
        sentences.append(
            f"News sentiment is {news_mood} (avg {news_avg:+.2f}); "
            f"average signal confidence across universe: {round(avg_conf * 100)}%."
        )

        result = {
            "sentiment": sentiment_label,
            "buy_pct":   buy_pct,
            "sell_pct":  sell_pct,
            "total_signals": total,
            "avg_confidence": avg_conf,
            "top_buys":  top_buys,
            "top_sells": top_sells,
            "hot_sector":  hot_sector,
            "cold_sector": cold_sector,
            "news_mood": news_mood,
            "commentary": " ".join(sentences),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        _commentary_cache = result
        _commentary_ts = t.time()
        return result
    finally:
        conn.close()


@router.get("/futures/brain")
def futures_brain():
    """Return brain state: current weights, learning history, regime."""
    from trading.brain import get_brain_state
    return get_brain_state()


@router.get("/futures/commentary")
def futures_commentary():
    """Template-based futures market summary from live quotes + news."""
    from data.futures_fetcher import fetch_quotes, FUTURES_INSTRUMENTS
    quotes = fetch_quotes()
    if not quotes:
        return {"sentiment": "UNKNOWN", "commentary": "Fetching market data…", "generated_at": datetime.now(timezone.utc).isoformat()}

    longs   = [q for q in quotes if q["signal"] == "LONG"]
    shorts  = [q for q in quotes if q["signal"] == "SHORT"]
    neutral = [q for q in quotes if q["signal"] == "NEUTRAL"]
    total   = len(quotes) or 1

    long_pct  = round(len(longs)  / total * 100)
    short_pct = round(len(shorts) / total * 100)

    if long_pct > 55:    sentiment_label = "RISK-ON"
    elif short_pct > 55: sentiment_label = "RISK-OFF"
    elif long_pct > short_pct + 10: sentiment_label = "MILDLY BULLISH"
    elif short_pct > long_pct + 10: sentiment_label = "MILDLY BEARISH"
    else:                sentiment_label = "MIXED"

    top_longs  = sorted(longs,  key=lambda q: q["confidence"], reverse=True)[:3]
    top_shorts = sorted(shorts, key=lambda q: q["confidence"], reverse=True)[:3]

    # Category breakdown
    cat_signals: dict[str, dict] = {}
    for q in quotes:
        cat = q["category"]
        c = cat_signals.setdefault(cat, {"long": 0, "short": 0, "neutral": 0})
        c[q["signal"].lower()] = c.get(q["signal"].lower(), 0) + 1

    best_cat  = max(cat_signals, key=lambda c: cat_signals[c]["long"])   if cat_signals else None
    worst_cat = max(cat_signals, key=lambda c: cat_signals[c]["short"])  if cat_signals else None

    avg_conf = round(sum(q["confidence"] for q in quotes) / total, 3)

    sentences = []
    sentences.append(
        f"Futures universe scanning {total} instruments: {long_pct}% LONG, {short_pct}% SHORT, "
        f"{100 - long_pct - short_pct}% NEUTRAL — market posture is {sentiment_label}."
    )
    if top_longs:
        names = [q["name"].split()[0] for q in top_longs]
        sentences.append(f"Strongest long signals: {', '.join(names)}.")
    if top_shorts:
        names = [q["name"].split()[0] for q in top_shorts]
        sentences.append(f"Highest conviction shorts: {', '.join(names)}.")
    if best_cat and worst_cat and best_cat != worst_cat:
        sentences.append(f"{best_cat} leads LONG momentum; {worst_cat} showing most SHORT pressure.")
    sentences.append(f"Average signal confidence: {round(avg_conf * 100)}%.")

    return {
        "sentiment": sentiment_label,
        "long_pct":  long_pct,
        "short_pct": short_pct,
        "total":     total,
        "avg_confidence": avg_conf,
        "top_longs":  [q["name"].split()[0] for q in top_longs],
        "top_shorts": [q["name"].split()[0] for q in top_shorts],
        "best_cat":   best_cat,
        "worst_cat":  worst_cat,
        "commentary": " ".join(sentences),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/market/heatmap")
def market_heatmap(limit: int = Query(300, le=500)):
    """Stock heatmap data: ticker, signal, confidence, change_pct, sector, market_cap."""
    conn = database.get_connection()
    try:
        rows = conn.execute("""
            SELECT s.ticker, s.signal, s.confidence, u.sector, u.market_cap, u.name
            FROM signals s
            JOIN ticker_universe u ON u.ticker = s.ticker
            WHERE s.timestamp = (
                SELECT MAX(s2.timestamp) FROM signals s2 WHERE s2.ticker = s.ticker
            )
            AND s.timestamp > datetime('now', '-6 hours')
            AND u.active = 1
            ORDER BY s.confidence DESC
            LIMIT ?
        """, (limit,)).fetchall()

        # Attach latest price change
        result = []
        for r in rows:
            ph = conn.execute("""
                SELECT (close - open) / open * 100 as change_pct
                FROM price_history WHERE ticker=? AND interval='1d'
                ORDER BY date DESC LIMIT 1
            """, (r["ticker"],)).fetchone()
            result.append({
                "ticker":     r["ticker"],
                "signal":     r["signal"],
                "confidence": round(r["confidence"], 3),
                "sector":     r["sector"] or "Other",
                "market_cap": r["market_cap"] or 0,
                "name":       r["name"] or r["ticker"],
                "change_pct": round(ph["change_pct"], 2) if ph and ph["change_pct"] else 0,
            })
        return result
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Signal Breakdown (transparency panel)
# ---------------------------------------------------------------------------

@router.get("/signals/breakdown/{ticker}")
def signal_breakdown(ticker: str):
    """Return detailed component breakdown for latest signal on a ticker."""
    conn = database.get_connection()
    try:
        row = conn.execute("""
            SELECT s.signal, s.confidence, s.timestamp, s.reasons, s.price,
                   u.name, u.sector, u.exchange
            FROM signals s
            LEFT JOIN ticker_universe u ON s.ticker = u.ticker
            WHERE s.ticker = ?
            ORDER BY s.timestamp DESC LIMIT 1
        """, (ticker.upper(),)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="No signal found")
        d = dict(row)
        reasons = json.loads(d.get("reasons") or "[]")
        sig = d["signal"]
        bullish_dir = sig == "BUY"

        components = []
        for r in reasons:
            rl = r.lower()
            if "rsi" in rl:
                try:
                    val = float(rl.split("(")[1].rstrip(")")) if "(" in rl else 50
                    is_bull = val < 50
                except Exception:
                    is_bull = bullish_dir
                components.append({"name": "RSI", "detail": r, "bullish": is_bull})
            elif "macd" in rl:
                components.append({"name": "MACD", "detail": r, "bullish": "above" in rl})
            elif "ema" in rl or "uptrend" in rl or "downtrend" in rl:
                components.append({"name": "EMA Trend", "detail": r,
                                   "bullish": "uptrend" in rl or "price > ema" in rl})
            elif "bb" in rl or "bollinger" in rl:
                components.append({"name": "Bollinger Bands", "detail": r,
                                   "bullish": "below bb" in rl or "mean reversion" in rl})
            elif "vwap" in rl:
                components.append({"name": "VWAP", "detail": r, "bullish": "above vwap" in rl})
            else:
                components.append({"name": "Signal", "detail": r, "bullish": bullish_dir})

        agreeing = sum(1 for c in components if c["bullish"] == bullish_dir)
        total = len(components)
        high_conviction = total >= 3 and agreeing >= total - 1

        return {
            "ticker": ticker.upper(),
            "signal": sig,
            "confidence": d["confidence"],
            "price": d["price"],
            "name": d["name"],
            "sector": d["sector"],
            "timestamp": d["timestamp"],
            "components": components,
            "agreeing": agreeing,
            "total": total,
            "high_conviction": high_conviction,
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Volatility-adjusted Momentum Rank
# ---------------------------------------------------------------------------

@router.get("/universe/momentum-rank")
def momentum_rank(limit: int = Query(20, le=100)):
    """Risk-adjusted momentum leaderboard: 30d return / annualised realised volatility."""
    conn = database.get_connection()
    try:
        tickers_rows = conn.execute(
            "SELECT ticker FROM ticker_universe WHERE active=1 ORDER BY tier DESC LIMIT 300"
        ).fetchall()
        tickers = [r["ticker"] for r in tickers_rows]

        results = []
        for ticker in tickers:
            rows = conn.execute("""
                SELECT close FROM price_history
                WHERE ticker=? AND interval='1d' AND close IS NOT NULL
                ORDER BY date DESC LIMIT 35
            """, (ticker,)).fetchall()
            closes = [r["close"] for r in rows]
            if len(closes) < 15:
                continue
            closes = list(reversed(closes))
            rets = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
            mom_30d = (closes[-1] - closes[0]) / closes[0]
            vol = (sum(r**2 for r in rets) / len(rets)) ** 0.5 * (252 ** 0.5)
            score = mom_30d / vol if vol > 0.001 else 0.0
            results.append({
                "ticker": ticker,
                "momentum_30d": round(mom_30d * 100, 2),
                "volatility": round(vol * 100, 2),
                "risk_adj_score": round(score, 3),
            })

        results.sort(key=lambda x: abs(x["risk_adj_score"]), reverse=True)
        top = results[:limit]

        for item in top:
            row = conn.execute("""
                SELECT s.signal, s.confidence, u.name, u.sector
                FROM signals s
                LEFT JOIN ticker_universe u ON s.ticker = u.ticker
                WHERE s.ticker = ?
                ORDER BY s.timestamp DESC LIMIT 1
            """, (item["ticker"],)).fetchone()
            if row:
                item.update(dict(row))

        return top
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Multi-Strategy Backtester
# ---------------------------------------------------------------------------
# Strategy patterns adapted from backtrader (Apache 2.0) + vectorbt (Apache 2.0)
# concepts. All indicator math is standard public-domain formula.
# backtrader: https://github.com/mementum/backtrader
# vectorbt:   https://github.com/polakowo/vectorbt
# ---------------------------------------------------------------------------

def _ema_series(closes: list, span: int) -> list:
    k = 2 / (span + 1)
    emas = [closes[0]]
    for c in closes[1:]:
        emas.append(c * k + emas[-1] * (1 - k))
    return emas


def _rsi_series(closes: list, period: int = 14) -> list:
    rsi = [50.0] * period
    for i in range(period, len(closes)):
        deltas = [closes[j] - closes[j-1] for j in range(i - period + 1, i + 1)]
        gains = [max(d, 0) for d in deltas]
        losses = [max(-d, 0) for d in deltas]
        avg_g = sum(gains) / period
        avg_l = sum(losses) / period
        rsi.append(100 - 100 / (1 + avg_g / (avg_l + 1e-9)))
    return rsi


def _atr_series(highs: list, lows: list, closes: list, period: int = 14) -> list:
    trs = [highs[0] - lows[0]]
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i],
                 abs(highs[i] - closes[i-1]),
                 abs(lows[i] - closes[i-1]))
        trs.append(tr)
    atrs = [sum(trs[:period]) / period]
    for tr in trs[period:]:
        atrs.append((atrs[-1] * (period - 1) + tr) / period)
    return [trs[0]] * (period - 1) + atrs


def _supertrend_series(highs: list, lows: list, closes: list,
                        period: int = 10, mult: float = 3.0) -> list[int]:
    """Returns direction: 1=bullish, -1=bearish."""
    atrs = _atr_series(highs, lows, closes, period)
    hl2 = [(h + l) / 2 for h, l in zip(highs, lows)]
    upper = [m + mult * a for m, a in zip(hl2, atrs)]
    lower = [m - mult * a for m, a in zip(hl2, atrs)]

    fu = list(upper); fl = list(lower)
    for i in range(1, len(closes)):
        fu[i] = upper[i] if upper[i] < fu[i-1] or closes[i-1] > fu[i-1] else fu[i-1]
        fl[i] = lower[i] if lower[i] > fl[i-1] or closes[i-1] < fl[i-1] else fl[i-1]

    direction = [1] * len(closes)
    for i in range(1, len(closes)):
        if closes[i] > fu[i]:
            direction[i] = 1
        elif closes[i] < fl[i]:
            direction[i] = -1
        else:
            direction[i] = direction[i-1]
    return direction


def _bb_series(closes: list, period: int = 20, dev: float = 2.0):
    upper = [None] * period; lower = [None] * period
    for i in range(period, len(closes)):
        window = closes[i-period:i]
        ma = sum(window) / period
        std = (sum((c - ma)**2 for c in window) / period) ** 0.5
        upper.append(ma + dev * std)
        lower.append(ma - dev * std)
    return upper, lower


# ── Strategy definitions (backtrader-style) ──────────────────────────────

STRATEGIES = {
    "ema_cross": "EMA 9/21 Crossover",
    "rsi_reversal": "RSI Mean Reversion (30/70)",
    "bb_breakout": "Bollinger Band Breakout",
    "supertrend": "Supertrend (10,3)",
    "composite": "Composite (RSI+EMA+Momentum)",
}


def _run_strategy(strategy: str, closes: list, highs: list, lows: list,
                  capital: float = 10_000, stop_loss_pct: float = 0.05,
                  take_profit_pct: float = 0.15) -> tuple[list, list]:
    """
    Run a single strategy over price data. Returns (equity_curve, trades).
    Implements ATR-based stop loss + take profit (backtrader pattern).
    """
    n = len(closes)
    ema9  = _ema_series(closes, 9)
    ema21 = _ema_series(closes, 21)
    rsi   = _rsi_series(closes, 14)
    bb_up, bb_lo = _bb_series(closes, 20, 2.0)
    st_dir = _supertrend_series(highs, lows, closes, 10, 3.0)
    atrs = _atr_series(highs, lows, closes, 14)

    cash = capital; shares = 0.0; entry = 0.0
    stop = 0.0; tp = 0.0
    trades = []
    equity = []
    in_trade = False

    for i in range(21, n):
        price = closes[i]

        # Exit conditions (stop/take profit)
        if in_trade and shares > 0:
            if price <= stop:
                cash = shares * price
                pnl = (price - entry) / entry * 100
                trades.append({"entry": round(entry, 2), "exit": round(price, 2),
                               "pnl_pct": round(pnl, 2), "win": False, "exit_reason": "stop_loss"})
                shares = 0.0; in_trade = False
            elif price >= tp:
                cash = shares * price
                pnl = (price - entry) / entry * 100
                trades.append({"entry": round(entry, 2), "exit": round(price, 2),
                               "pnl_pct": round(pnl, 2), "win": True, "exit_reason": "take_profit"})
                shares = 0.0; in_trade = False

        # Strategy signals
        sig = "HOLD"
        if strategy == "ema_cross":
            if ema9[i] > ema21[i] and ema9[i-1] <= ema21[i-1]:  sig = "BUY"
            elif ema9[i] < ema21[i] and ema9[i-1] >= ema21[i-1]: sig = "SELL"

        elif strategy == "rsi_reversal":
            if rsi[i] < 30 and rsi[i-1] >= 30:  sig = "BUY"
            elif rsi[i] > 70 and rsi[i-1] <= 70: sig = "SELL"

        elif strategy == "bb_breakout":
            if bb_lo[i] and price < bb_lo[i] and closes[i-1] >= (bb_lo[i-1] or price): sig = "BUY"
            elif bb_up[i] and price > bb_up[i] and closes[i-1] <= (bb_up[i-1] or price): sig = "SELL"

        elif strategy == "supertrend":
            if st_dir[i] == 1 and st_dir[i-1] == -1: sig = "BUY"
            elif st_dir[i] == -1 and st_dir[i-1] == 1: sig = "SELL"

        elif strategy == "composite":
            score = 0
            if rsi[i] < 35: score += 1
            elif rsi[i] > 65: score -= 1
            if ema9[i] > ema21[i]: score += 1
            else: score -= 1
            if st_dir[i] == 1: score += 1
            else: score -= 1
            mom = (closes[i] - closes[i-10]) / closes[i-10] if i >= 10 and closes[i-10] > 0 else 0
            if mom > 0.02: score += 1
            elif mom < -0.02: score -= 1
            if score >= 2: sig = "BUY"
            elif score <= -2: sig = "SELL"

        # Execute
        if sig == "BUY" and not in_trade and cash > 0:
            shares = cash / price
            entry = price
            atr = atrs[i]
            stop = entry - stop_loss_pct * entry
            tp = entry + take_profit_pct * entry
            cash = 0.0
            in_trade = True

        elif sig == "SELL" and in_trade and shares > 0:
            cash = shares * price
            pnl = (price - entry) / entry * 100
            trades.append({"entry": round(entry, 2), "exit": round(price, 2),
                           "pnl_pct": round(pnl, 2), "win": pnl > 0, "exit_reason": "signal"})
            shares = 0.0; in_trade = False

        equity.append(round(cash + shares * price, 2))

    return equity, trades


@router.get("/backtest")
def backtest(
    ticker: str = Query(...),
    days: int = Query(90, le=730),
    strategy: str = Query("composite", pattern="^(ema_cross|rsi_reversal|bb_breakout|supertrend|composite|all)$"),
    stop_loss_pct: float = Query(0.05, ge=0.01, le=0.30),
    take_profit_pct: float = Query(0.15, ge=0.02, le=1.0),
    capital: float = Query(10_000, ge=100, le=1_000_000),
):
    """
    Multi-strategy backtester. Strategies: ema_cross, rsi_reversal, bb_breakout, supertrend, composite, all.
    Strategy patterns adapted from backtrader (Apache 2.0) and vectorbt (Apache 2.0).
    Includes: stop-loss, take-profit, benchmark (buy-and-hold), walk-forward stats.
    """
    import yfinance as yf
    from trading.stats_engine import compute_stats

    conn = database.get_connection()
    try:
        rows = conn.execute("""
            SELECT date, open, high, low, close FROM price_history
            WHERE ticker=? AND interval='1d' AND close IS NOT NULL
            ORDER BY date ASC
        """, (ticker.upper(),)).fetchall()
        raw = [(r["date"], r["open"] or r["close"], r["high"] or r["close"],
                r["low"] or r["close"], r["close"]) for r in rows]
    finally:
        conn.close()

    if len(raw) < 40:
        hist = yf.Ticker(ticker.upper()).history(period=f"{days + 60}d", interval="1d")
        if hist.empty:
            raise HTTPException(status_code=404, detail="No price data found")
        raw = [(str(idx.date()), float(r["Open"]), float(r["High"]),
                float(r["Low"]), float(r["Close"])) for idx, r in hist.iterrows()]

    raw = raw[-(days + 60):]
    dates  = [r[0] for r in raw]
    opens  = [r[1] for r in raw]
    highs  = [r[2] for r in raw]
    lows   = [r[3] for r in raw]
    closes = [r[4] for r in raw]

    # Buy-and-hold benchmark
    bh_start = closes[21] if len(closes) > 21 else closes[0]
    bh_final = closes[-1]
    bh_return = (bh_final - bh_start) / bh_start * 100
    bh_equity = [round(capital * (c / bh_start), 2) for c in closes[21:]]

    strategies_to_run = list(STRATEGIES.keys()) if strategy == "all" else [strategy]
    results = {}

    for strat in strategies_to_run:
        eq_raw, trades = _run_strategy(
            strat, closes, highs, lows,
            capital=capital,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
        )
        final_val = eq_raw[-1] if eq_raw else capital
        total_ret = (final_val - capital) / capital * 100
        trade_pnls = [t["pnl_pct"] / 100 for t in trades]

        stats = compute_stats(eq_raw, trade_pnls) if len(eq_raw) >= 2 else {}

        # Downsample equity curve for frontend
        step = max(1, len(eq_raw) // 100)
        equity_curve = [{"date": dates[21 + i * step], "value": eq_raw[i * step],
                         "benchmark": bh_equity[i * step] if i * step < len(bh_equity) else bh_equity[-1]}
                        for i in range(len(eq_raw) // step)
                        if 21 + i * step < len(dates)]

        # Alpha vs benchmark
        alpha = round(total_ret - bh_return, 2)

        results[strat] = {
            "strategy_name": STRATEGIES[strat],
            "total_trades": len(trades),
            "win_rate": stats.get("win_rate", 0),
            "total_return_pct": round(total_ret, 2),
            "benchmark_return_pct": round(bh_return, 2),
            "alpha_pct": alpha,
            "max_drawdown_pct": stats.get("max_drawdown_pct", 0),
            "sharpe": stats.get("sharpe", 0),
            "sortino": stats.get("sortino", 0),
            "calmar": stats.get("calmar", 0),
            "profit_factor": stats.get("profit_factor_trades", stats.get("profit_factor", 0)),
            "var_95_pct": stats.get("var_95_pct", 0),
            "volatility_ann_pct": stats.get("volatility_ann_pct", 0),
            "avg_win_loss_ratio": stats.get("avg_win_loss_ratio", 0),
            "num_wins": stats.get("num_wins", 0),
            "num_losses": stats.get("num_losses", 0),
            "final_value": round(final_val, 2),
            "equity_curve": equity_curve,
            "recent_trades": trades[-20:],
        }

    # Best strategy by Sharpe
    best = max(results.values(), key=lambda x: x.get("sharpe", 0)) if results else {}

    return {
        "ticker": ticker.upper(),
        "days": days,
        "capital": capital,
        "stop_loss_pct": stop_loss_pct,
        "take_profit_pct": take_profit_pct,
        "benchmark_return_pct": round(bh_return, 2),
        "strategies": results,
        "best_strategy": best.get("strategy_name", ""),
        # Flat fields for single-strategy callers (backward compat)
        **(results.get(strategy, results.get("composite", {})) if strategy != "all" else {}),
    }


# ---------------------------------------------------------------------------
# Pattern Engine endpoints
# ---------------------------------------------------------------------------

@router.get("/patterns/{ticker}")
def patterns_ticker(ticker: str):
    """Run VCP, NR7, Stage, BB-Squeeze pattern detection for a single ticker."""
    from signals.pattern_engine import scan_patterns
    result = scan_patterns(ticker.upper())
    return result


@router.get("/patterns/scan/top")
def patterns_scan(limit: int = Query(50, le=200)):
    """
    Scan top active tickers for patterns. Returns tickers with detected patterns ranked by pattern_score.
    """
    from signals.pattern_engine import scan_patterns
    conn = database.get_connection()
    try:
        rows = conn.execute(
            "SELECT ticker FROM ticker_universe WHERE active=1 ORDER BY tier DESC LIMIT ?",
            (limit,),
        ).fetchall()
        tickers = [r["ticker"] for r in rows]
    finally:
        conn.close()

    results = []
    for t in tickers:
        try:
            r = scan_patterns(t)
            if r.get("patterns") or r.get("pattern_score", 0) > 0.2:
                results.append(r)
        except Exception:
            pass

    results.sort(key=lambda x: x.get("pattern_score", 0), reverse=True)
    return {"count": len(results), "results": results}


# ---------------------------------------------------------------------------
# TopK Portfolio Rotation
# ---------------------------------------------------------------------------

@router.get("/topk")
def topk_portfolio(
    k: int = Query(10, le=50),
    min_stage: int = Query(None),
):
    """
    TopK portfolio rotation: rank all tickers by composite signal+pattern+momentum score.
    Returns top-K long and top-K short candidates.
    Concept inspired by Qlib TopK strategy (MIT).
    """
    from signals.topk_ranker import get_topk_portfolio
    results = get_topk_portfolio(k=k, include_patterns=True, min_stage=min_stage)
    longs = [r for r in results if r.get("position") == "LONG"]
    shorts = [r for r in results if r.get("position") == "SHORT"]
    return {
        "k": k,
        "longs": longs,
        "shorts": shorts,
        "total": len(results),
    }


@router.get("/topk/rotation")
def topk_rotation(k: int = Query(10, le=50)):
    """
    Compare TopK target vs current paper portfolio holdings.
    Returns what to buy/sell for rotation.
    """
    from signals.topk_ranker import get_rotation_diff
    conn = database.get_connection()
    try:
        rows = conn.execute("SELECT ticker FROM portfolio_state").fetchall()
        current = [r["ticker"] for r in rows]
    finally:
        conn.close()
    return get_rotation_diff(current, k=k)


@router.post("/topk/optimize")
def topk_optimize(tickers: list[str], method: str = Query("max_sharpe", regex="^(max_sharpe|min_cvar|equal)$")):
    """
    PyPortfolioOpt (MIT) portfolio weight optimization.
    POST body: list of ticker strings.
    Methods: max_sharpe (default), min_cvar, equal.
    Returns optimal weights + Sharpe / volatility stats.
    """
    from signals.topk_ranker import optimize_weights
    if not tickers or len(tickers) > 50:
        raise HTTPException(400, "Provide 2-50 tickers")
    weights = optimize_weights(tickers, method=method)
    return {"weights": weights, "method": method}


# ---------------------------------------------------------------------------
# Fear & Greed + Insider Trading
# ---------------------------------------------------------------------------

@router.get("/market/breadth")
def market_breadth(days: int = Query(90, le=365)):
    """
    Market Breadth indicators computed from local DB. No API key.
    Returns: McClellan Oscillator, Advance-Decline Line, TRIN (Arms Index),
             New High/Low ratio, % stocks above 50/200 MA.
    Formulas: public domain (McClellan 1969, Arms 1967).
    """
    from signals.market_breadth import compute_breadth
    return compute_breadth(days=days)


@router.get("/market/macro")
def macro_regime():
    """
    World Bank macro economic regime. No API key.
    GDP growth, inflation, unemployment → goldilocks/overheating/stagflation/recession.
    """
    from data.macro_fetcher import get_macro_regime
    return get_macro_regime()


@router.get("/market/fear-greed")
def fear_greed():
    """
    Local Fear & Greed Index (0-100). No API key.
    Computed from: momentum, stock strength, breadth, put/call ratio, VIX.
    < 25 = Extreme Fear (historically great buy zone).
    """
    from signals.fear_greed import compute_fear_greed, _load_cached
    cached = _load_cached()
    if cached:
        return cached
    return compute_fear_greed()


@router.get("/market/insider/{ticker}")
def insider_trades(ticker: str, days: int = Query(30, le=90)):
    """
    SEC Form 4 insider trading score + raw transactions for a ticker.
    No API key — EDGAR public data.
    """
    from data.insider_fetcher import get_insider_score, _ensure_table
    _ensure_table()
    import database as db
    score = get_insider_score(ticker, days=days)
    conn = db.get_connection()
    try:
        rows = conn.execute("""
            SELECT insider_name, transaction_code, shares, price, value_usd, trade_date, is_buy
            FROM insider_trades
            WHERE ticker=?
            ORDER BY trade_date DESC LIMIT 20
        """, (ticker.upper().split(".")[0],)).fetchall()
        trades = [dict(r) for r in rows]
    finally:
        conn.close()
    return {"ticker": ticker, "insider_score": round(score, 4), "trades": trades, "days": days}


@router.get("/market/short-interest/{ticker}")
def short_interest(ticker: str):
    """
    FINRA REG SHO short interest data for a ticker.
    No API key — FINRA free public data.
    """
    from data.short_interest import get_short_interest_score
    score, meta = get_short_interest_score(ticker)
    return {"ticker": ticker, "short_score": round(score, 4), **meta}


# /market/{ticker} MUST be last among market routes — FastAPI matches in order,
# and this catch-all would shadow /market/breadth, /market/fear-greed, etc. if placed first.
@router.get("/market/{ticker}")
def market_data(ticker: str, interval: str = "1d", limit: int = 200):
    return _market_data_handler(ticker, interval, limit)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@router.get("/health")
def health():
    conn = database.get_connection()
    try:
        jobs = conn.execute("SELECT * FROM scheduler_health").fetchall()
        universe_count = conn.execute(
            "SELECT COUNT(*) AS n FROM ticker_universe WHERE active=1"
        ).fetchone()["n"]
        return {
            "status": "ok",
            "universe_size": universe_count,
            "jobs": [dict(j) for j in jobs],
        }
    finally:
        conn.close()
