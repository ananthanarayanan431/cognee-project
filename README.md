# DebateMind

An AI-powered debate training app that helps you sharpen your argumentation skills through adversarial practice. DebateMind pairs you with an adaptive AI opponent that learns your logical weaknesses and challenges you with targeted counterarguments, while tracking your argument patterns over time.

## Features

- **Live Debate** — Chat with an AI opponent that responds with streaming word-by-word text, then scores your argument on Logic, Evidence, and Rhetoric
- **Cognitive Fingerprint** — Visual graph tracking your recurring argument patterns and logical fallacies over time
- **Topic Selection** — Choose from curated policy, technology, and society topics or get a random surprise
- **Difficulty Levels** — Balanced, Targeted (exploits your known weaknesses), or Ruthless
- **Progress Dashboard** — Track win rate, session streaks, and mastered patterns across all topics
- **Session Summary** — See before/after fingerprint changes and which fallacies you've eliminated

## Tech Stack

**Backend:**
- FastAPI (Python) with PostgreSQL
- SSE (Server-Sent Events) for streaming debate responses
- Cognee for knowledge graph storage and recall
- JWT authentication

**Frontend:**
- Next.js with React & TypeScript
- TailwindCSS for styling
- D3.js for fingerprint graph visualization
- WebSocket for real-time updates

## Setup

### Prerequisites

- Node.js 18+ and npm
- Python 3.9+
- Docker (for PostgreSQL)
- Git

### Quick Start

1. **Start PostgreSQL:**
   ```bash
   docker run -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=debatemind -p 5432:5432 -d postgres:16
   ```

2. **Run both backend and frontend in parallel:**
   ```bash
   make dev
   ```

   Or run separately:
   ```bash
   # Terminal 1: Backend
   make debatemind-backend

   # Terminal 2: Frontend
   make frontend
   ```

3. **Open the app:**
   Navigate to [http://localhost:3000](http://localhost:3000)

### Individual Setup

**Backend:**
```bash
cd debatemind-backend
source venv/bin/activate
pip install -r requirements.txt
uvicorn debatemind.main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

## Environment Variables

### Frontend (`frontend/.env.local`)
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### Backend (`debatemind-backend/.env`)
```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5437/debatemind
SECRET_KEY=<random-secret>
OPENROUTER_API_KEY=<your-openrouter-key>
# Optional: override default models (any OpenRouter slug works)
# FAST_MODEL=google/gemini-flash-1.5
# MAIN_MODEL=meta-llama/llama-3.1-70b-instruct

# Cognee backend mode: "local" (default, self-hosted via the cognee-db service
# in docker-compose.yml) or "cloud" (Cognee Cloud's hosted API).
COGNEE_MODE=local
COGNEE_LLM_API_KEY=<anthropic-key-cognee-uses-for-its-own-llm-calls>
# Only used when COGNEE_MODE=cloud:
COGNEE_API_KEY=<your-cognee-cloud-key>
```

See `debatemind-backend/.env.example` for the full list of `COGNEE_DB_*` overrides
(only relevant when `COGNEE_MODE=local`, and only needed if you changed the
`cognee-db` service in `docker-compose.yml`).

## Available Commands

- `make debatemind-backend` — Start FastAPI backend on port 8000
- `make frontend` — Start Next.js frontend on port 3000
- `make dev` — Run both simultaneously with parallel jobs

## Architecture

The app follows a three-tier architecture:

1. **Frontend (Next.js)** — User interface with real-time WebSocket updates
2. **Backend (FastAPI)** — Debate logic, AI orchestration, and session management
3. **Database (PostgreSQL)** — User profiles, sessions, and cognitive fingerprints

Key flows:
- User registers → creates cognitive fingerprint node in Cognee
- User starts debate → FastAPI spawns AI opponent, streams responses via SSE
- Judge agent scores rounds → fingerprint updates after session
- Mastery tracking → identifies patterns for targeted difficulty next session
