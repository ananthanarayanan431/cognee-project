#!/bin/bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

# Colors
RESET="\033[0m"
BOLD="\033[1m"

C_DB="\033[36m"       # cyan
C_BACKEND="\033[35m"  # magenta
C_FRONTEND="\033[34m" # blue
C_INFO="\033[33m"     # yellow
C_OK="\033[32m"       # green
C_ERR="\033[31m"      # red

label() {
  local color="$1" tag="$2"
  # prefix every line from stdin with a colored tag
  while IFS= read -r line; do
    echo -e "${color}${BOLD}[${tag}]${RESET} ${line}"
  done
}

# Cleanup on exit
cleanup() {
  echo -e "\n${C_INFO}${BOLD}[run.sh] Shutting down...${RESET}"
  kill 0
}
trap cleanup EXIT INT TERM

echo -e "${C_INFO}${BOLD}========================================${RESET}"
echo -e "${C_INFO}${BOLD}  DebateMind — starting services        ${RESET}"
echo -e "${C_INFO}${BOLD}========================================${RESET}"

# ── 1. Start Postgres ────────────────────────────────────────────────────────
echo -e "${C_DB}${BOLD}[db] Starting postgres on port 5437...${RESET}"
docker compose up -d 2>&1 | label "$C_DB" "db"

echo -e "${C_DB}${BOLD}[db] Waiting for postgres to be ready...${RESET}"
until docker compose exec db pg_isready -U postgres -q 2>/dev/null; do
  sleep 1
done
echo -e "${C_OK}${BOLD}[db] Postgres is ready ✓${RESET}"

# ── 2. Start Backend ─────────────────────────────────────────────────────────
echo -e "${C_BACKEND}${BOLD}[backend] Starting FastAPI on http://localhost:8001${RESET}"
(
  cd "$ROOT/debatemind-backend"
  uv run uvicorn debatemind.main:app --reload --port 8001 2>&1 | label "$C_BACKEND" "backend"
) &

# ── 3. Start Frontend ────────────────────────────────────────────────────────
echo -e "${C_FRONTEND}${BOLD}[frontend] Starting Next.js on http://localhost:3000${RESET}"
(
  cd "$ROOT/frontend"
  npm run dev 2>&1 | label "$C_FRONTEND" "frontend"
) &

echo -e "${C_OK}${BOLD}[run.sh] All services started. Press Ctrl+C to stop.${RESET}"
echo -e "${C_INFO}  DB       → localhost:5437${RESET}"
echo -e "${C_BACKEND}  Backend  → http://localhost:8001${RESET}"
echo -e "${C_FRONTEND}  Frontend → http://localhost:3000${RESET}"

wait
