"""
APScheduler tiered job definitions.
"""

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

import database

logger = logging.getLogger(__name__)


def _record_job(job_name: str, status: str, error: str = None):
    conn = database.get_connection()
    try:
        conn.execute("""
            INSERT INTO scheduler_health (job_name, last_run, last_status, error_msg, run_count)
            VALUES (?,?,?,?,1)
            ON CONFLICT(job_name) DO UPDATE SET
                last_run=excluded.last_run,
                last_status=excluded.last_status,
                error_msg=excluded.error_msg,
                run_count=run_count+1
        """, (job_name, datetime.now(timezone.utc).isoformat(), status, error))
        conn.commit()
    finally:
        conn.close()


def _wrap(job_name: str, fn):
    def wrapper():
        try:
            fn()
            _record_job(job_name, "ok")
        except Exception as exc:
            logger.error("Job %s failed: %s", job_name, exc, exc_info=True)
            _record_job(job_name, "error", str(exc))
    wrapper.__name__ = job_name
    return wrapper


def create_scheduler() -> BackgroundScheduler:
    from data.universe_manager import refresh_universe, update_tier_classification
    from data.market_fetcher import fetch_tier0_eod, fetch_tier1_intraday, fetch_tier2_intraday, fetch_tier2_5min, compute_price_correlations
    from data.news_crawler import crawl as news_crawl
    from data.reddit_crawler import crawl as reddit_crawl
    from data.sec_fetcher import fetch_tier_fundamentals
    from data.insider_fetcher import fetch_recent_insider_trades
    from data.short_interest import fetch_short_interest
    from data.macro_fetcher import fetch_macro_data
    from data.yfinance_fundamentals import fetch_yfinance_fundamentals
    from data.sentiment_scorer import score_new_articles
    from graph.neo4j_builder import run_full_graph_update
    from graph.gnn_model import train as gnn_train
    from signals.signal_engine import run_signal_generation
    from trading.paper_trader import evaluate_positions, process_signals
    from trading.futures_trader import evaluate_futures_positions
    from trading.futures_auto_trader import run_auto_trade

    def signal_and_trade():
        sigs = run_signal_generation()
        if sigs:
            process_signals(sigs)

    scheduler = BackgroundScheduler(timezone="UTC")

    # Daily jobs
    scheduler.add_job(_wrap("universe_refresh", refresh_universe),
                      CronTrigger(hour=6, minute=0), id="universe_refresh", replace_existing=True)

    scheduler.add_job(_wrap("tier0_eod", fetch_tier0_eod),
                      CronTrigger(hour=7, minute=0), id="tier0_eod", replace_existing=True)

    scheduler.add_job(_wrap("fundamentals", fetch_tier_fundamentals),
                      CronTrigger(hour=7, minute=30), id="fundamentals", replace_existing=True)

    # Real sector + fundamentals from yfinance (daily after EOD)
    scheduler.add_job(_wrap("yf_fundamentals", fetch_yfinance_fundamentals),
                      CronTrigger(hour=8, minute=0), id="yf_fundamentals", replace_existing=True)

    # Insider trades: EDGAR Form 4 — daily after market close (no API key)
    scheduler.add_job(_wrap("insider_trades", fetch_recent_insider_trades),
                      CronTrigger(hour=9, minute=0), id="insider_trades", replace_existing=True)

    # Short interest: FINRA REG SHO — twice weekly (bimonthly data, check daily)
    scheduler.add_job(_wrap("short_interest", fetch_short_interest),
                      CronTrigger(hour=9, minute=30), id="short_interest", replace_existing=True)

    # World Bank macro data — weekly (annual data, no need to fetch more often)
    scheduler.add_job(_wrap("macro_data", fetch_macro_data),
                      CronTrigger(day_of_week="mon", hour=6, minute=30), id="macro_data", replace_existing=True)

    # Real price correlations (daily after prices fetched)
    scheduler.add_job(_wrap("price_correlations", compute_price_correlations),
                      CronTrigger(hour=8, minute=30), id="price_correlations", replace_existing=True)

    scheduler.add_job(_wrap("graph_update", run_full_graph_update),
                      CronTrigger(hour=20, minute=0), id="graph_update", replace_existing=True)

    # Weekly — GNN retrain on Sunday 02:00 UTC
    scheduler.add_job(_wrap("gnn_train", gnn_train),
                      CronTrigger(day_of_week="sun", hour=2, minute=0), id="gnn_train", replace_existing=True)

    # Hourly jobs
    # Hourly jobs — staggered by 10min each
    scheduler.add_job(_wrap("tier_classification", update_tier_classification),
                      IntervalTrigger(minutes=60, start_date="2000-01-01 00:00:00"), id="tier_classification", replace_existing=True)

    scheduler.add_job(_wrap("tier1_intraday", fetch_tier1_intraday),
                      IntervalTrigger(minutes=60, start_date="2000-01-01 00:10:00"), id="tier1_intraday", replace_existing=True)

    scheduler.add_job(_wrap("news_crawl", news_crawl),
                      IntervalTrigger(minutes=60, start_date="2000-01-01 00:20:00"), id="news_crawl", replace_existing=True)

    scheduler.add_job(_wrap("sentiment", score_new_articles),
                      IntervalTrigger(minutes=60, start_date="2000-01-01 00:30:00"), id="sentiment", replace_existing=True)

    # 5-min price fetch — yfinance only, no API key
    scheduler.add_job(_wrap("tier2_5min", fetch_tier2_5min),
                      IntervalTrigger(minutes=5), id="tier2_5min", replace_existing=True)

    scheduler.add_job(_wrap("signals", signal_and_trade),
                      IntervalTrigger(seconds=30), id="signals", replace_existing=True)

    scheduler.add_job(_wrap("position_check", evaluate_positions),
                      IntervalTrigger(seconds=30), id="position_check", replace_existing=True)

    scheduler.add_job(_wrap("futures_position_check", evaluate_futures_positions),
                      IntervalTrigger(seconds=30), id="futures_position_check", replace_existing=True)

    scheduler.add_job(_wrap("futures_auto_trade", run_auto_trade),
                      IntervalTrigger(seconds=30), id="futures_auto_trade", replace_existing=True)

    # 30-min jobs
    scheduler.add_job(_wrap("reddit_crawl", reddit_crawl),
                      IntervalTrigger(minutes=30, start_date="2000-01-01 00:12:00"), id="reddit_crawl", replace_existing=True)

    return scheduler
