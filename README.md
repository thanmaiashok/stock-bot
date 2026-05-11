# StockBot

> AI-powered paper trading bot covering 18 000+ stocks (US NYSE/NASDAQ + India NSE/BSE).  
> Zero paid APIs. Runs fully local. Open source.

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688)
![React](https://img.shields.io/badge/React-18-61DAFB)
![License](https://img.shields.io/badge/license-MIT-green)

---

## What it does

StockBot continuously screens 18 000+ tickers, runs a four-model ensemble on the top candidates, and executes paper trades when confidence exceeds 70 %.

```
Universe (18k+ tickers)
    │
    ├─ Tier 0 — daily EOD fetch (all filtered stocks)
    ├─ Tier 1 — hourly intraday   (top 1 000 active candidates)
    └─ Tier 2 — 15-min deep analysis (top 200 stocks)
                    │
                    ├─ GraphSAGE GNN        35 %
                    ├─ XGBoost (technicals) 25 %
                    ├─ FinBERT sentiment    20 %
                    └─ SEC fundamentals     20 %
                                │
                          BUY / SELL / HOLD
                          (paper wallet only)
```

**Signal sources** — all free, no API keys required except Reddit (optional):

| Exchange | Source |
|----------|--------|
| NASDAQ   | `ftp.nasdaqtrader.com` |
| NYSE/AMEX | `ftp.nasdaqtrader.com` |
| NSE India | `archives.nseindia.com` |
| BSE India | BSE bhavcopy ZIP (daily) |

Liquidity filter: price > \$0.50 / ₹10, 30-day avg volume > 100k shares.

---

## Stack

| Layer | Tech |
|-------|------|
| Backend API | FastAPI + APScheduler |
| ML models | XGBoost, PyTorch Geometric (GraphSAGE), HuggingFace FinBERT |
| Graph DB | Neo4j 5 Community (Docker) |
| Storage | SQLite (local) |
| Frontend | React 18 + Vite + Tailwind CSS |

---

## Quick start (one command)

```bash
git clone https://github.com/YOUR_USERNAME/stock-bot.git
cd stock-bot
cp .env.example .env   # add Reddit creds if you want sentiment (optional)
./start.sh
```

`start.sh` handles everything: checks prerequisites, starts Neo4j via Docker, creates a Python venv, installs deps, and launches backend + frontend.

| Service | URL |
|---------|-----|
| UI | http://localhost:5173 |
| API | http://localhost:8000 |
| API docs | http://localhost:8000/docs |
| Neo4j browser | http://localhost:7474 |

Stop with `./kill.sh`.

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (for Neo4j)
- Python 3.11 or 3.12
- Node 18+

---

## First-run steps

### 1. Seed the stock universe (~18k tickers, ~2 min)

```bash
cd backend
source ~/.stockbot-venv/bin/activate
python -c "from data.universe_manager import refresh_universe; refresh_universe()"
```

This runs automatically every day at 06:00 UTC after the first seed.

### 2. Train the GNN (optional — pre-trained weights included)

```bash
python -c "from graph.gnn_model import train; train()"
```

The GNN also trains automatically on startup if no checkpoint exists.

---

## Environment variables

Copy `.env.example` to `.env` and fill in:

| Variable | Required | Description |
|----------|----------|-------------|
| `NEO4J_URI` | auto | Set by docker-compose |
| `NEO4J_USER` | auto | Set by docker-compose |
| `NEO4J_PASSWORD` | auto | Set by docker-compose |
| `DATABASE_PATH` | auto | SQLite path |
| `PAPER_WALLET_USD` | no | Starting balance (default `10000`) |
| `REDDIT_CLIENT_ID` | no | Reddit app client ID |
| `REDDIT_CLIENT_SECRET` | no | Reddit app secret |
| `REDDIT_USER_AGENT` | no | Reddit user-agent string |

Reddit credentials are only needed for the sentiment scorer. Create a free app at  
https://www.reddit.com/prefs/apps (type: **script**).

---

## API reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/signals` | Latest signals for all Tier 2 stocks |
| GET | `/api/signals/{ticker}` | Signal history for one stock |
| GET | `/api/portfolio` | Current paper portfolio |
| GET | `/api/portfolio/history` | Trade history |
| GET | `/api/portfolio/stats` | Win rate, Sharpe ratio, P&L |
| GET | `/api/market/{ticker}` | OHLCV + technicals |
| GET | `/api/news/{ticker}` | News + FinBERT sentiment |
| GET | `/api/graph/correlations/{ticker}` | Correlated stocks (Neo4j) |
| GET | `/api/graph/sector/{sector}` | All stocks in a sector |
| GET | `/api/universe/stats` | Universe size + tier breakdown |
| GET | `/api/universe/screener` | Filter / search all 18k+ stocks |
| POST | `/api/watchlist/add` | Force a ticker into Tier 2 |
| GET | `/api/health` | Scheduler job status |

Full interactive docs at `/docs` (Swagger UI) and `/redoc`.

---

## Frontend pages

- **Dashboard** — top signals, portfolio summary, universe stats
- **Signal Feed** — all signals with per-model score breakdown
- **Stock Detail** — candlestick chart, technicals, news, correlations
- **Portfolio** — positions, P&L chart, full trade history
- **Screener** — search / filter all 18k+ stocks
- **Watchlist** — manage Tier 2 forced tickers
- **Graph Explorer** — interactive Neo4j correlation graph

---

## Paper trading rules

- Starting wallet: \$10 000 (configurable via `PAPER_WALLET_USD`)
- Entry: confidence > 70 %
- Stop loss: 2× ATR below entry
- Take profit: 3 : 1 risk-reward ratio
- **No real money is ever touched.** This is a simulation only.

---

## Full Docker setup (alternative)

If you prefer everything in containers:

```bash
docker-compose up --build
```

FinBERT (~400 MB) downloads from HuggingFace on first start and is cached in a Docker volume forever after.

---

## Project structure

```
stock-bot/
├── backend/
│   ├── api/          # FastAPI routes
│   ├── data/         # Fetchers (market, news, SEC, Reddit, macro, …)
│   ├── signals/      # Signal engine, technical features, risk, ranker
│   ├── graph/        # GNN model + Neo4j builder
│   ├── trading/      # Paper trader + futures auto trader
│   ├── models/       # Saved model weights (XGBoost + GNN)
│   ├── main.py       # App entry point
│   ├── scheduler.py  # APScheduler job definitions
│   ├── database.py   # SQLite init
│   └── config.py     # Env-var config
├── frontend/
│   └── src/          # React + Vite + Tailwind
├── docker-compose.yml
├── start.sh          # One-command launcher
├── kill.sh           # Stop all services
└── .env.example      # Config template
```

---

## Contributing

Pull requests welcome. Please:

1. Fork the repo and create a feature branch.
2. Keep changes focused — one feature / fix per PR.
3. Run `pip install -r backend/requirements.txt` and make sure the backend starts cleanly.
4. Open a PR with a clear description of what changed and why.

For larger changes, open an issue first to discuss the approach.

---

## License

MIT — see [LICENSE](LICENSE).

> **Disclaimer:** StockBot is a research and educational tool. It trades paper money only. Nothing here is financial advice.
