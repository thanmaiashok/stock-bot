import sqlite3
import logging
import os
from config import DATABASE_PATH

logger = logging.getLogger(__name__)


def get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=10000")
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS ticker_universe (
            ticker          TEXT PRIMARY KEY,
            exchange        TEXT NOT NULL,
            name            TEXT,
            sector          TEXT,
            industry        TEXT,
            tier            INTEGER DEFAULT 0,
            last_price      REAL,
            avg_volume_30d  REAL,
            market_cap      REAL,
            currency        TEXT,
            active          INTEGER DEFAULT 1,
            last_updated    TEXT
        );

        CREATE TABLE IF NOT EXISTS price_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker      TEXT NOT NULL,
            date        TEXT NOT NULL,
            interval    TEXT NOT NULL,
            open        REAL,
            high        REAL,
            low         REAL,
            close       REAL,
            volume      REAL,
            UNIQUE(ticker, date, interval)
        );
        CREATE INDEX IF NOT EXISTS idx_price_ticker_date ON price_history(ticker, date);
        CREATE INDEX IF NOT EXISTS idx_price_interval ON price_history(interval);

        CREATE TABLE IF NOT EXISTS news_articles (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            url_hash        TEXT UNIQUE NOT NULL,
            headline        TEXT NOT NULL,
            url             TEXT,
            source          TEXT,
            published_at    TEXT,
            ticker_mentions TEXT,
            futures_mentions TEXT,
            sentiment_score  REAL,
            sentiment_done  INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_news_published ON news_articles(published_at);
        CREATE INDEX IF NOT EXISTS idx_news_sentiment ON news_articles(sentiment_done);

        CREATE TABLE IF NOT EXISTS social_mentions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker      TEXT NOT NULL,
            source      TEXT NOT NULL,
            text        TEXT,
            score       REAL DEFAULT 0,
            created_at  TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_social_ticker ON social_mentions(ticker, created_at);

        CREATE TABLE IF NOT EXISTS fundamentals (
            ticker          TEXT PRIMARY KEY,
            pe_ratio        REAL,
            eps             REAL,
            revenue_growth  REAL,
            profit_margin   REAL,
            debt_to_equity  REAL,
            current_ratio   REAL,
            roe             REAL,
            sector_pe       REAL,
            updated_at      TEXT
        );

        CREATE TABLE IF NOT EXISTS sentiment_scores (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker          TEXT NOT NULL,
            date            TEXT NOT NULL,
            positive        REAL DEFAULT 0,
            negative        REAL DEFAULT 0,
            neutral         REAL DEFAULT 0,
            article_count   INTEGER DEFAULT 0,
            composite_score REAL DEFAULT 0,
            UNIQUE(ticker, date)
        );
        CREATE INDEX IF NOT EXISTS idx_sentiment_ticker_date ON sentiment_scores(ticker, date);

        CREATE TABLE IF NOT EXISTS signals (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker              TEXT NOT NULL,
            timestamp           TEXT NOT NULL,
            signal              TEXT NOT NULL,
            confidence          REAL NOT NULL,
            gnn_score           REAL,
            xgb_score           REAL,
            sentiment_score     REAL,
            fundamental_score   REAL,
            reasons             TEXT,
            tier                INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_signals_ticker ON signals(ticker, timestamp);

        CREATE TABLE IF NOT EXISTS paper_trades (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker      TEXT NOT NULL,
            action      TEXT NOT NULL,
            quantity    REAL NOT NULL,
            price       REAL NOT NULL,
            timestamp   TEXT NOT NULL,
            pnl         REAL DEFAULT 0,
            reason      TEXT
        );

        CREATE TABLE IF NOT EXISTS portfolio_state (
            ticker      TEXT PRIMARY KEY,
            quantity    REAL NOT NULL,
            avg_entry   REAL NOT NULL,
            stop_loss   REAL,
            take_profit REAL,
            opened_at   TEXT
        );

        CREATE TABLE IF NOT EXISTS portfolio_cash (
            id          INTEGER PRIMARY KEY CHECK (id = 1),
            cash_usd    REAL NOT NULL,
            updated_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS scheduler_health (
            job_name    TEXT PRIMARY KEY,
            last_run    TEXT,
            last_status TEXT,
            error_msg   TEXT,
            run_count   INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS futures_positions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol      TEXT NOT NULL UNIQUE,
            direction   TEXT NOT NULL,
            units       REAL NOT NULL,
            entry_price REAL NOT NULL,
            margin_used REAL NOT NULL,
            stop_loss   REAL,
            take_profit REAL,
            opened_at   TEXT,
            updated_at  TEXT
        );

        CREATE TABLE IF NOT EXISTS futures_trades (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol    TEXT NOT NULL,
            direction TEXT NOT NULL,
            action    TEXT NOT NULL,
            units     REAL NOT NULL,
            price     REAL NOT NULL,
            margin    REAL NOT NULL,
            pnl       REAL,
            timestamp TEXT NOT NULL,
            reason    TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_futures_trades_sym ON futures_trades(symbol, timestamp);

        CREATE TABLE IF NOT EXISTS futures_cash (
            id         INTEGER PRIMARY KEY CHECK (id = 1),
            cash_usd   REAL NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS futures_auto_config (
            id                  INTEGER PRIMARY KEY CHECK (id = 1),
            enabled             INTEGER DEFAULT 1,
            confidence_threshold REAL DEFAULT 0.55,
            units_per_trade     REAL DEFAULT 1.0,
            max_open_positions  INTEGER DEFAULT 5,
            updated_at          TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS brain_state (
            id               INTEGER PRIMARY KEY CHECK (id = 1),
            momentum_w       REAL NOT NULL DEFAULT 0.30,
            ema_w            REAL NOT NULL DEFAULT 0.25,
            rsi_w            REAL NOT NULL DEFAULT 0.20,
            bbands_w         REAL NOT NULL DEFAULT 0.15,
            consistency_w    REAL NOT NULL DEFAULT 0.10,
            learning_episodes INTEGER NOT NULL DEFAULT 0,
            recent_win_rate  REAL NOT NULL DEFAULT 0.5,
            regime           TEXT NOT NULL DEFAULT 'UNKNOWN',
            updated_at       TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS brain_log (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            momentum_w     REAL,
            ema_w          REAL,
            rsi_w          REAL,
            bbands_w       REAL,
            consistency_w  REAL,
            win_rate       REAL,
            regime         TEXT,
            episode        INTEGER,
            timestamp      TEXT NOT NULL
        );
    """)

    # Migrate tables — add columns if missing
    for table, col, definition in [
        ("news_articles",     "futures_mentions",    "TEXT"),
        ("news_articles",     "sentiment_score",     "REAL"),
        ("futures_positions", "components_snapshot", "TEXT"),
        ("futures_trades",    "components_snapshot", "TEXT"),
        ("signals",           "price",               "REAL"),
    ]:
        try:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {definition}")
            logger.info("Migrated %s: added %s", table, col)
        except Exception:
            pass  # column already exists

    conn.commit()
    conn.close()
    logger.info("Database initialized at %s", DATABASE_PATH)
