<p align="center"><img src="docs/flow-3.svg" alt="Animated StockBot pipeline: Universe → Tier 0 → Tier 1 → Tier 2 → Ensemble → Decide" width="100%"/></p>

<p align="center"><sub>10-second tour: Universe → Tier 0 → Tier 1 → Tier 2 → Ensemble → Decide</sub></p>

<p align="center"><img src="docs/px3/intro.svg" width="100%" alt="AI-powered paper trading bot covering 18,000+ stocks (US NYSE/NASDAQ and India NSE/BSE). Zero paid APIs. Runs fully local. Open source."/></p>

<p align="center"><img src="docs/px3/features.svg" width="100%" alt="Key features"/></p>

<p align="center"><img src="docs/px3/divider.svg" width="100%" alt=""/></p>

<a id="what-it-does"></a>
<h2><img src="docs/px3/h2-what-it-does.svg" width="100%" alt="What it does"/></h2>

<p align="center"><img src="docs/px3/t-01.svg" width="100%" alt="StockBot continuously screens 18 000+ tickers, runs a four-model ensemble on the top candidates, and executes paper trades when confidence exceeds 70 %."/></p>

<p align="center"><img src="docs/px3/c-01.svg" width="100%" alt="code: Universe (18k+ tickers) │ ├─ Tier 0 — daily EOD fetch (all filtered stocks) ├─ Tier 1 — hourly intraday (top 1 000 active candidates) └─ Tier 2 — 15-min deep an"/></p>

<p align="center"><img src="docs/px3/t-02.svg" width="100%" alt="Signal sources - all free, no API keys required except Reddit (optional): Exchange | Source NASDAQ | ftp.nasdaqtrader.com NYSE/AMEX | ftp.nasdaqtrader.com NSE India | archives.nseindia.com BSE India | BSE bhavcopy ZIP (daily) Liquidity filter: price &gt; $0.50 / 10, 30-day avg volume &gt; 100k shares."/></p>

<p align="center"><img src="docs/px3/divider.svg" width="100%" alt=""/></p>

<a id="stack"></a>
<h2><img src="docs/px3/h2-stack.svg" width="100%" alt="Stack"/></h2>

<p align="center"><img src="docs/px3/t-03.svg" width="100%" alt="Layer | Tech Backend API | FastAPI + APScheduler ML models | XGBoost, PyTorch Geometric (GraphSAGE), HuggingFace FinBERT Graph DB | Neo4j 5 Community (Docker) Storage | SQLite (local) Frontend | React 18 + Vite + Tailwind CSS"/></p>

<p align="center"><img src="docs/px3/divider.svg" width="100%" alt=""/></p>

<a id="quick-start-one-command"></a>
<h2><img src="docs/px3/h2-quick-start-one-command.svg" width="100%" alt="Quick start (one command)"/></h2>

<p align="center"><img src="docs/px3/c-02.svg" width="100%" alt="code: git clone https://github.com/thanmaiashok/stock-bot.git cd stock-bot cp .env.example .env # add Reddit creds if you want sentiment (optional) ./start.sh "/></p>

<p align="center"><img src="docs/px3/t-04.svg" width="100%" alt="start.sh handles everything: checks prerequisites, starts Neo4j via Docker, creates a Python venv, installs deps, and launches backend + frontend. Service | URL UI | http://localhost:5173 API | http://localhost:8000 API docs | http://localhost:8000/docs Neo4j browser | http://localhost:7474 Stop with ./kill.sh."/></p>

<a id="prerequisites"></a>
<h3><img src="docs/px3/h3-prerequisites.svg" width="100%" alt="Prerequisites"/></h3>

<p align="center"><img src="docs/px3/t-05.svg" width="100%" alt="Docker Desktop (for Neo4j) Python 3.11 or 3.12 Node 18+"/></p>

<p align="center"><a href="https://www.docker.com/products/docker-desktop/"><img src="docs/px3/link-01.svg" height="34" alt="Docker Desktop"/></a></p>

<p align="center"><img src="docs/px3/divider.svg" width="100%" alt=""/></p>

<a id="first-run-steps"></a>
<h2><img src="docs/px3/h2-first-run-steps.svg" width="100%" alt="First-run steps"/></h2>

<a id="1-seed-the-stock-universe-18k-tickers-2-min"></a>
<h3><img src="docs/px3/h3-1-seed-the-stock-universe-18k-tickers-2-min.svg" width="100%" alt="1. Seed the stock universe (~18k tickers, ~2 min)"/></h3>

<p align="center"><img src="docs/px3/c-03.svg" width="100%" alt="code: cd backend source ~/.stockbot-venv/bin/activate python -c &quot;from data.universe_manager import refresh_universe; refresh_universe()&quot; "/></p>

<p align="center"><img src="docs/px3/t-06.svg" width="100%" alt="This runs automatically every day at 06:00 UTC after the first seed."/></p>

<a id="2-train-the-gnn-optional--pre-trained-weights-included"></a>
<h3><img src="docs/px3/h3-2-train-the-gnn-optional-pre-trained-weights-included.svg" width="100%" alt="2. Train the GNN (optional — pre-trained weights included)"/></h3>

<p align="center"><img src="docs/px3/c-04.svg" width="100%" alt="code: python -c &quot;from graph.gnn_model import train; train()&quot; "/></p>

<p align="center"><img src="docs/px3/t-07.svg" width="100%" alt="The GNN also trains automatically on startup if no checkpoint exists."/></p>

<p align="center"><img src="docs/px3/divider.svg" width="100%" alt=""/></p>

<a id="environment-variables"></a>
<h2><img src="docs/px3/h2-environment-variables.svg" width="100%" alt="Environment variables"/></h2>

<p align="center"><img src="docs/px3/t-08.svg" width="100%" alt="Copy .env.example to .env and fill in: Variable | Required | Description NEO4J_URI | auto | Set by docker-compose NEO4J_USER | auto | Set by docker-compose NEO4J_PASSWORD | auto | Set by docker-compose DATABASE_PATH | auto | SQLite path PAPER_WALLET_USD | no | Starting balance (default 10000) REDDIT_CLIENT_ID | no | Reddit app client ID REDDIT_CLIENT_SECRET | no | Reddit app secret REDDIT_USER_AGENT | no | Reddit user-agent string Reddit credentials are only needed for the sentiment scorer. Create a free app athttps://www.reddit.com/prefs/apps (type: script)."/></p>

<p align="center"><img src="docs/px3/divider.svg" width="100%" alt=""/></p>

<a id="api-reference"></a>
<h2><img src="docs/px3/h2-api-reference.svg" width="100%" alt="API reference"/></h2>

<p align="center"><img src="docs/px3/t-09.svg" width="100%" alt="Method | Endpoint | Description GET | /api/signals | Latest signals for all Tier 2 stocks GET | /api/signals/{ticker} | Signal history for one stock GET | /api/portfolio | Current paper portfolio GET | /api/portfolio/history | Trade history GET | /api/portfolio/stats | Win rate, Sharpe ratio, P&amp;L GET | /api/market/{ticker} | OHLCV + technicals GET | /api/news/{ticker} | News + FinBERT sentiment GET | /api/graph/correlations/{ticker} | Correlated stocks (Neo4j) GET | /api/graph/sector/{sector} | All stocks in a sector GET | /api/universe/stats | Universe size + tier breakdown GET | /api/universe/screener | Filter / search all 18k+ stocks POST | /api/watchlist/add | Force a ticker into Tier 2 GET | /api/health | Scheduler job status Full interactive docs at /docs (Swagger UI) and /redoc."/></p>

<p align="center"><img src="docs/px3/divider.svg" width="100%" alt=""/></p>

<a id="frontend-pages"></a>
<h2><img src="docs/px3/h2-frontend-pages.svg" width="100%" alt="Frontend pages"/></h2>

<p align="center"><img src="docs/px3/t-10.svg" width="100%" alt="Dashboard - top signals, portfolio summary, universe stats Signal Feed - all signals with per-model score breakdown Stock Detail - candlestick chart, technicals, news, correlations Portfolio - positions, P&amp;L chart, full trade history Screener - search / filter all 18k+ stocks Watchlist - manage Tier 2 forced tickers Graph Explorer - interactive Neo4j correlation graph"/></p>

<p align="center"><img src="docs/px3/divider.svg" width="100%" alt=""/></p>

<a id="paper-trading-rules"></a>
<h2><img src="docs/px3/h2-paper-trading-rules.svg" width="100%" alt="Paper trading rules"/></h2>

<p align="center"><img src="docs/px3/t-11.svg" width="100%" alt="Starting wallet: $10 000 (configurable via PAPER_WALLET_USD) Entry: confidence &gt; 70 % Stop loss: 2x ATR below entry Take profit: 3 : 1 risk-reward ratio No real money is ever touched. This is a simulation only."/></p>

<p align="center"><img src="docs/px3/divider.svg" width="100%" alt=""/></p>

<a id="full-docker-setup-alternative"></a>
<h2><img src="docs/px3/h2-full-docker-setup-alternative.svg" width="100%" alt="Full Docker setup (alternative)"/></h2>

<p align="center"><img src="docs/px3/t-12.svg" width="100%" alt="If you prefer everything in containers:"/></p>

<p align="center"><img src="docs/px3/c-05.svg" width="100%" alt="code: docker-compose up --build "/></p>

<p align="center"><img src="docs/px3/t-13.svg" width="100%" alt="FinBERT (~400 MB) downloads from HuggingFace on first start and is cached in a Docker volume forever after."/></p>

<p align="center"><img src="docs/px3/divider.svg" width="100%" alt=""/></p>

<a id="project-structure"></a>
<h2><img src="docs/px3/h2-project-structure.svg" width="100%" alt="Project structure"/></h2>

<p align="center"><img src="docs/px3/c-06.svg" width="100%" alt="code: stock-bot/ ├── backend/ │ ├── api/ # FastAPI routes │ ├── data/ # Fetchers (market, news, SEC, Reddit, macro, …) │ ├── signals/ # Signal engine, technical featu"/></p>

<p align="center"><img src="docs/px3/divider.svg" width="100%" alt=""/></p>

<a id="contributing"></a>
<h2><img src="docs/px3/h2-contributing.svg" width="100%" alt="Contributing"/></h2>

<p align="center"><img src="docs/px3/t-14.svg" width="100%" alt="Pull requests welcome. Please: Fork the repo and create a feature branch. Keep changes focused - one feature / fix per PR. Run pip install -r backend/requirements.txt and make sure the backend starts cleanly. Open a PR with a clear description of what changed and why. For larger changes, open an issue first to discuss the approach."/></p>

<p align="center"><img src="docs/px3/divider.svg" width="100%" alt=""/></p>

<a id="license"></a>
<h2><img src="docs/px3/h2-license.svg" width="100%" alt="License"/></h2>

<p align="center"><img src="docs/px3/t-15.svg" width="100%" alt="MIT - see LICENSE. Disclaimer: StockBot is a research and educational tool. It trades paper money only. Nothing here is financial advice."/></p>

<p align="center"><a href="LICENSE"><img src="docs/px3/link-02.svg" height="34" alt="LICENSE"/></a></p>

<p align="center"><img src="docs/px3/divider.svg" width="100%" alt=""/></p>

<p align="center"><a href="https://github.com/thanmaiashok"><img src="docs/px3/footer.svg" width="100%" alt="Built by Thanmai A, founder of FoxynAI"/></a></p>
