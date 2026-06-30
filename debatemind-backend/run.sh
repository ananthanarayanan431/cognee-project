#!/bin/sh
set -e

cd "$(dirname "$0")"

RESET="\033[0m"
BOLD="\033[1m"
C_BACKEND="\033[35m"
C_OK="\033[32m"

log() { printf "${C_BACKEND}${BOLD}[backend]${RESET} %s\n" "$1"; }
ok()  { printf "${C_OK}${BOLD}[backend]${RESET} %s\n" "$1"; }

# Create venv only if it doesn't exist yet
if [ ! -f ".venv/bin/uvicorn" ]; then
  log "Setting up virtual environment (first run only)..."
  uv sync
  ok "Environment ready ✓"
fi

# Run alembic migrations
log "Running database migrations..."
.venv/bin/alembic upgrade head
ok "Migrations applied ✓"

ok "Starting FastAPI on http://localhost:8001"
.venv/bin/uvicorn debatemind.main:app --reload --port 8001
