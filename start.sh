#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${GREEN}[StockBot]${NC} $1"; }
warn() { echo -e "${YELLOW}[StockBot]${NC} $1"; }
die() { echo -e "${RED}[StockBot ERROR]${NC} $1"; exit 1; }

# ── Check prerequisites ────────────────────────────────────────────────────
command -v docker >/dev/null 2>&1 || die "Docker not installed. Install Docker Desktop: https://www.docker.com/products/docker-desktop/"
command -v python3 >/dev/null 2>&1 || die "Python 3 not found."
command -v node >/dev/null 2>&1 || die "Node.js not found. Install Node 18+."
command -v npm >/dev/null 2>&1 || die "npm not found."

# ── Start Docker Desktop if daemon not running ─────────────────────────────
if ! docker info >/dev/null 2>&1; then
    warn "Docker daemon not running. Launching Docker Desktop..."
    open -a Docker 2>/dev/null || die "Could not launch Docker Desktop. Open it manually and re-run ./start.sh"

    log "Waiting for Docker daemon (up to 60s)..."
    for i in $(seq 1 30); do
        if docker info >/dev/null 2>&1; then
            log "Docker daemon ready."
            break
        fi
        if [ "$i" -eq 30 ]; then
            die "Docker daemon still not ready after 60s. Open Docker Desktop manually and re-run ./start.sh"
        fi
        sleep 2
    done
fi

# ── .env check ────────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
    warn ".env not found — copying from .env.example"
    cp .env.example .env
fi

# ── Neo4j via Docker ──────────────────────────────────────────────────────
log "Starting Neo4j (Docker)..."
docker compose up -d neo4j

log "Waiting for Neo4j to be ready (up to 60s)..."
for i in $(seq 1 30); do
    if docker compose exec -T neo4j neo4j status 2>/dev/null | grep -q "running"; then
        log "Neo4j ready."
        break
    fi
    if [ "$i" -eq 30 ]; then
        warn "Neo4j health check timed out — it may still be starting. Continuing..."
    fi
    sleep 2
done

# ── Python dependencies ───────────────────────────────────────────────────
log "Installing Python dependencies..."
cd backend

# Find Python 3.11 or 3.12 — pandas has no wheel for 3.14 yet
# Also venv must be OUTSIDE this path (apostrophe in dir name breaks meson INI parser)
VENV_DIR="$HOME/.stockbot-venv"

PYTHON=""
for candidate in python3.12 python3.11 python3.13; do
    if command -v "$candidate" >/dev/null 2>&1; then
        VER=$("$candidate" -c "import sys; print(sys.version_info.minor)")
        MAJOR=$("$candidate" -c "import sys; print(sys.version_info.major)")
        if [ "$MAJOR" -eq 3 ] && [ "$VER" -le 13 ]; then
            PYTHON=$(command -v "$candidate")
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    die "Need Python 3.11–3.13 (pandas has no wheel for 3.14 yet). Install with: brew install python@3.12"
fi

log "Using Python: $PYTHON ($($PYTHON --version))"
log "Venv location: $VENV_DIR  (outside path-with-apostrophe to avoid meson bug)"

if [ ! -d "$VENV_DIR" ]; then
    log "Creating Python virtualenv..."
    "$PYTHON" -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
log "Python deps installed."

# ── Node dependencies ─────────────────────────────────────────────────────
log "Installing frontend dependencies..."
cd ../frontend
npm install --silent
log "Frontend deps installed."

# ── Kill any stale StockBot processes before starting ─────────────────────
log "Cleaning up stale processes..."
cd "$SCRIPT_DIR"
bash kill.sh >/dev/null 2>&1 || true
sleep 1
cd "$SCRIPT_DIR/backend"
source "$HOME/.stockbot-venv/bin/activate"

# ── Start backend ─────────────────────────────────────────────────────────
BACKEND_PORT=8000
log "Starting FastAPI backend (port $BACKEND_PORT)..."

mkdir -p data models logs

STOCKBOT_PORT=$BACKEND_PORT nohup uvicorn main:app --host 0.0.0.0 --port $BACKEND_PORT --reload \
    > logs/backend.log 2>&1 &
BACKEND_PID=$!
echo $BACKEND_PID > logs/backend.pid
echo $BACKEND_PORT > logs/backend.port
log "Backend PID: $BACKEND_PID → logs/backend.log"

# Wait for backend (fail loudly if it doesn't come up)
BACKEND_READY=0
for i in $(seq 1 20); do
    if curl -sf http://localhost:$BACKEND_PORT/ >/dev/null 2>&1; then
        log "Backend ready at http://localhost:$BACKEND_PORT"
        BACKEND_READY=1
        break
    fi
    sleep 2
done
if [ "$BACKEND_READY" -eq 0 ]; then
    warn "Backend did not respond after 40s — check logs/backend.log for errors"
fi

# ── Start frontend ────────────────────────────────────────────────────────
log "Starting Vite frontend (port 5173)..."
cd ../frontend

VITE_API_PORT=$BACKEND_PORT nohup npm run dev \
    > ../backend/logs/frontend.log 2>&1 &
FRONTEND_PID=$!
echo $FRONTEND_PID > ../backend/logs/frontend.pid
log "Frontend PID: $FRONTEND_PID → backend/logs/frontend.log"

sleep 3

# ── Done ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║         StockBot is running!             ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║  UI:      http://localhost:5173          ║${NC}"
echo -e "${GREEN}║  API:     http://localhost:$BACKEND_PORT          ║${NC}"
echo -e "${GREEN}║  API docs:http://localhost:$BACKEND_PORT/docs     ║${NC}"
echo -e "${GREEN}║  Neo4j:   http://localhost:7474          ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║  Stop: ./kill.sh                         ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
echo ""

warn "First run: seed the universe (~18k tickers, no rate limits):"
warn "  cd backend && source ~/.stockbot-venv/bin/activate"
warn "  python -c \"from data.universe_manager import refresh_universe; refresh_universe()\""
