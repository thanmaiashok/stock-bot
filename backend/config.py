import os
from dotenv import load_dotenv

load_dotenv()

# Neo4j
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "stockbot123")

# Database
DATABASE_PATH = os.getenv("DATABASE_PATH", "./data/stockbot.db")

# Paper wallet
PAPER_WALLET_USD = float(os.getenv("PAPER_WALLET_USD", "10000"))

# Universe / tier thresholds
MIN_PRICE_USD = 0.50
MIN_PRICE_INR = 10.0
MIN_AVG_VOLUME_30D = 100_000

TIER1_SIZE = 1000       # top movers/volume from filtered universe
TIER2_SIZE = 500        # active candidates for hourly fetch
DEEP_ANALYSIS_SIZE = 200  # deep technicals + GNN + signals

# Signal generation — stocks (weights must sum to 1.0)
SIGNAL_CONFIDENCE_THRESHOLD = 0.20   # lowered from 0.7 — trades now fire
GNN_WEIGHT = 0.27
XGB_WEIGHT = 0.20
SENTIMENT_WEIGHT = 0.16
FUNDAMENTAL_WEIGHT = 0.13
PATTERN_WEIGHT = 0.14
INSIDER_WEIGHT = 0.10  # SEC Form 4 insider trades — highly predictive alpha

# Signal generation — futures (must sum to 1.0)
FUTURES_MOMENTUM_WEIGHT    = 0.30   # price change magnitude + direction
FUTURES_EMA_WEIGHT         = 0.25   # EMA5 vs EMA20 separation
FUTURES_RSI_WEIGHT         = 0.20   # overbought/oversold mean-reversion
FUTURES_BBANDS_WEIGHT      = 0.15   # Bollinger Band position (new)
FUTURES_CONSISTENCY_WEIGHT = 0.10   # triple-EMA trend alignment

# Risk
MAX_POSITION_PCT = 0.10        # 10% of portfolio per stock
ATR_STOP_MULTIPLIER = 2.0
RISK_REWARD_RATIO = 3.0
VAR_CONFIDENCE = 0.95

# Aggressive trading controls
MAX_CONCURRENT_POSITIONS = 8   # never hold more than 8 stocks at once
MAX_HOLD_HOURS = 24            # force-sell if stuck longer than this
TRAILING_STOP_PCT = 0.03       # trail stop 3% below highest seen price
MOMENTUM_BURST_PCT = 0.02      # 2% price move in one 5m candle = momentum entry
MOMENTUM_VOLUME_MULT = 1.8     # volume must be 1.8x avg to confirm burst

# Batch fetch settings
YFINANCE_BATCH_SIZE = 100
YFINANCE_BATCH_DELAY = 3.0  # seconds between batches
YFINANCE_MAX_RETRIES = 3

# Correlation graph
CORRELATION_THRESHOLD = 0.75
MAX_CROSS_SECTOR_PAIRS = 50  # per stock, to keep graph sparse

# RSS feeds
RSS_FEEDS = [
    "https://feeds.reuters.com/reuters/businessNews",
    "https://finance.yahoo.com/news/rssindex",
    "https://feeds.marketwatch.com/marketwatch/topstories",
    "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best",
]

