#!/bin/sh
set -e

cd "$(dirname "$0")"

RESET="\033[0m"
BOLD="\033[1m"
C_BACKEND="\033[35m"
C_OK="\033[32m"

log() { printf "${C_BACKEND}${BOLD}[backend]${RESET} %s\n" "$1"; }
ok()  { printf "${C_OK}${BOLD}[backend]${RESET} %s\n" "$1"; }

# Sync venv on first run or when dependency inputs have changed
_needs_sync=0
if [ ! -f ".venv/bin/uvicorn" ]; then
  _needs_sync=1
elif [ "pyproject.toml" -nt ".venv/bin/uvicorn" ] || [ "uv.lock" -nt ".venv/bin/uvicorn" ]; then
  _needs_sync=1
fi

if [ "$_needs_sync" = "1" ]; then
  log "Setting up virtual environment..."
  uv sync
  ok "Environment ready ✓"
fi

# Run alembic migrations
log "Running database migrations..."
.venv/bin/alembic upgrade head
ok "Migrations applied ✓"

ok "Starting FastAPI on http://localhost:8001"
.venv/bin/uvicorn debatemind.main:app --reload --port 8001
