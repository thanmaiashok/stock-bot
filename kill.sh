#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

log() { echo -e "${GREEN}[StockBot]${NC} $1"; }
warn() { echo -e "${RED}[StockBot]${NC} $1"; }

# ── Kill backend ──────────────────────────────────────────────────────────
BACKEND_PORT=8000
[ -f "backend/logs/backend.port" ] && BACKEND_PORT=$(cat backend/logs/backend.port)

if [ -f "backend/logs/backend.pid" ]; then
    PID=$(cat backend/logs/backend.pid)
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID" 2>/dev/null
        warn "Backend stopped (PID $PID)"
    fi
    rm -f backend/logs/backend.pid
fi

# Fallback: kill by stored port (catches orphaned uvicorn)
for PORT in "$BACKEND_PORT" 8000 8001; do
    PIDS=$(lsof -ti:"$PORT" 2>/dev/null)
    if [ -n "$PIDS" ]; then
        echo "$PIDS" | xargs kill 2>/dev/null
        warn "Killed process(es) on port $PORT"
        break
    fi
done

# Kill any lingering uvicorn
pkill -f "uvicorn main:app" 2>/dev/null && warn "Killed uvicorn process" || true

# ── Kill frontend ─────────────────────────────────────────────────────────
if [ -f "backend/logs/frontend.pid" ]; then
    PID=$(cat backend/logs/frontend.pid)
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID" 2>/dev/null
        warn "Frontend stopped (PID $PID)"
    fi
    rm -f backend/logs/frontend.pid
fi

# Fallback: kill by port
PIDS=$(lsof -ti:5173 2>/dev/null)
if [ -n "$PIDS" ]; then
    echo "$PIDS" | xargs kill 2>/dev/null
    warn "Killed process(es) on port 5173"
fi

# Kill any lingering vite/npm dev
pkill -f "vite" 2>/dev/null && warn "Killed vite process" || true

# ── Stop Neo4j Docker ─────────────────────────────────────────────────────
if command -v docker >/dev/null 2>&1; then
    log "Stopping Neo4j Docker container..."
    docker compose stop neo4j 2>/dev/null || true
fi

echo ""
log "All StockBot services stopped."
log "To restart: ./start.sh"
