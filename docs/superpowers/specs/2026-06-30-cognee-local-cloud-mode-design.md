# Configurable local/cloud Cognee backend

**Date:** 2026-06-30
**Status:** Approved

## Context

`debatemind-backend` uses the `cognee` Python SDK (`cognee==0.1.40`) embedded directly
in the FastAPI process via `debatemind/services/cognee_svc.py`. The current setup only
supports a cloud-oriented LLM config (`COGNEE_API_KEY` / `COGNEE_LLM_API_KEY` in
`main.py`), and the user has been hitting Cognee Cloud's capacity waitlist. They want a
self-hosted local backend as an alternative, switchable via `.env`, without removing the
existing cloud-oriented path, and with the local infra always available in
`docker-compose.yml`.

### Pre-existing bug discovered during research

`cognee_svc.py` calls `cognee.remember()`, `cognee.recall()`, and `cognee.improve()`.
None of these exist on the installed `cognee==0.1.40` package — confirmed by reading
`debatemind-backend/.venv/lib/python3.12/site-packages/cognee/__init__.py`, whose real
top-level API is `add`, `delete`, `cognify`, `config`, `datasets`, `prune`, `search`,
`visualize_graph`. Calling the current code crashes with `AttributeError` regardless of
local/cloud mode. This is fixed as part of this change (see below) — otherwise neither
mode would have anything working to switch between.

### Ground-truthed SDK internals

Read directly from the installed package (not just docs, since `0.1.40` predates much of
the public "Local Docker" documentation):

- `cognee.config.set_relational_db_config(dict)`, `set_vector_db_config(dict)`,
  `set_graph_db_config(dict)`, `set_llm_config(dict)` all validate dict keys with
  `hasattr()` against the underlying pydantic `BaseSettings` class and raise
  `InvalidAttributeError` for unknown keys.
- `RelationalConfig` fields: `db_provider` (default `"sqlite"`), `db_host`, `db_port`,
  `db_name`, `db_username`, `db_password`.
- `VectorConfig` fields: `vector_db_provider` (default `"lancedb"`); supports
  `pgvector`, which reuses `RelationalConfig`'s host/port/name/username/password (no
  separate vector host needed) — confirmed in
  `cognee/infrastructure/databases/vector/create_vector_engine.py`.
- `GraphConfig` fields: `graph_database_provider` (default `"NETWORKX"`); supports
  `kuzu` (file-based, no container) and `neo4j` — confirmed in
  `cognee/infrastructure/databases/graph/get_graph_engine.py`.
- pgvector adapter auto-runs `CREATE EXTENSION IF NOT EXISTS vector;` on first connect
  (`cognee/infrastructure/databases/vector/pgvector/create_db_and_tables.py`), so the
  Postgres image just needs the extension binary available (`pgvector/pgvector:pg16`).
- `cognee[postgres,kuzu]==0.1.40` extras pull in `psycopg2`, `pgvector`, and `kuzu`
  (confirmed via PyPI release metadata) — none of these are installed today.

## Design

### 1. `cognee_svc.py` — fix to use the real SDK API

Replace the nonexistent calls with the real ones, keeping the same function signatures
so callers (`pipeline.py`, `opponent.py`, `graph_svc.py`, `sessions.py`) don't change:

- `remember_argument(...)`: build the same fact-text block as today, then
  `await cognee.add(text, dataset_name=dataset)` followed by
  `await cognee.cognify(datasets=dataset)`.
- `recall_weaknesses(user_id)`: `await cognee.search(query_text=..., query_type=SearchType.GRAPH_COMPLETION, datasets=[dataset], top_k=10)`,
  importing `SearchType` from `cognee.modules.search.types` (re-exported by
  `cognee.api.v1.search.search`, so the existing import path also still works).
  Keep the existing `[{"text": ...}]` return shape since `opponent.py` and
  `graph_svc.py` depend on it.
- `improve_fingerprint(user_id, session_id)`: re-run `await cognee.cognify(datasets=dataset)`.
  There is no separate "improve" step in this SDK version; re-cognifying the dataset is
  the closest real equivalent (it incorporates anything added since the last cognify).
- `forget_pattern(user_id, pattern_type)`: same "MASTERED" marker text as today, written
  via `add` + `cognify` instead of the nonexistent `remember`.

### 2. Config (`debatemind/config.py`, `.env.example`)

Add to `Settings`:

```python
cognee_mode: str = "local"  # "local" | "cloud"
cognee_db_host: str = "localhost"
cognee_db_port: str = "5433"
cognee_db_name: str = "cognee"
cognee_db_username: str = "cognee"
cognee_db_password: str = "cognee"
```

Defaults match the new `cognee-db` compose service exactly, so a fresh `.env.example`
copy works with zero edits in local mode. `.env.example` gets a `COGNEE_MODE=local`
line plus the five `COGNEE_DB_*` lines (commented as only relevant to local mode), with
the existing `COGNEE_API_KEY` / `COGNEE_LLM_API_KEY` lines kept as-is for cloud mode.

### 3. `main.py` lifespan wiring

```python
if settings.cognee_mode == "local":
    cognee.config.set_relational_db_config({
        "db_provider": "postgres",
        "db_host": settings.cognee_db_host,
        "db_port": settings.cognee_db_port,
        "db_name": settings.cognee_db_name,
        "db_username": settings.cognee_db_username,
        "db_password": settings.cognee_db_password,
    })
    cognee.config.set_vector_db_config({"vector_db_provider": "pgvector"})
    cognee.config.set_graph_db_config({"graph_database_provider": "kuzu"})
    if settings.cognee_llm_api_key:
        cognee.config.set_llm_config({
            "provider": "anthropic",
            "model": "claude-haiku-4-5-20251001",
            "api_key": settings.cognee_llm_api_key,
        })
elif settings.cognee_mode == "cloud":
    if settings.cognee_api_key and settings.cognee_llm_api_key:
        cognee.config.set_llm_config({
            "provider": "anthropic",
            "model": "claude-haiku-4-5-20251001",
            "api_key": settings.cognee_llm_api_key,
        })
```

Cloud mode's branch is byte-for-byte what exists today (untouched), just moved behind
the mode check. Local mode leaves graph storage at Kuzu's own default file path
(`~/.cognee_system/databases/...`) — no extra path env var needed since the backend
runs natively (not containerized) for local dev, per the existing `run.sh` /
`Makefile` workflow.

### 4. `docker-compose.yml`

Add a `cognee-db` service, always defined (not profile-gated) so it starts on every
`docker compose up -d` / `make infra-up` / `run.sh` regardless of which `COGNEE_MODE`
is currently selected:

```yaml
  cognee-db:
    image: pgvector/pgvector:pg16
    restart: unless-stopped
    environment:
      POSTGRES_USER: cognee
      POSTGRES_PASSWORD: cognee
      POSTGRES_DB: cognee
    volumes:
      - cognee_pgdata:/var/lib/postgresql/data
    ports:
      - "5433:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U cognee"]
      interval: 5s
      timeout: 5s
      retries: 10
```

Add `cognee_pgdata:` to the top-level `volumes:` block alongside the existing `pgdata:`.
Port `5433` avoids collision with the app's own Postgres (mapped to `5437` on the host
per the in-progress `docker-compose.yml` diff already on this branch).

### 5. `pyproject.toml`

Change `"cognee==0.1.40"` to `"cognee[postgres,kuzu]==0.1.40"` to install the
`psycopg2`, `pgvector`, and `kuzu` packages the local-mode adapters import at runtime.

## Out of scope

- Running Cognee's own standalone API server container (the "local-server" alternative
  considered and explicitly declined in favor of keeping the embedded-SDK approach).
- Neo4j as a graph backend (Kuzu chosen — file-based, zero extra containers, matches
  Cognee's own newer-version default).
- Any change to the actual Cognee Cloud REST integration beyond gating its existing
  (already-correct) LLM config call behind `COGNEE_MODE=cloud`.

## Testing

- Unit-level: importing `cognee_svc.py` and exercising `remember_argument` /
  `recall_weaknesses` against the local Postgres+pgvector+Kuzu backend (no network
  calls beyond the LLM provider) to confirm the SDK calls succeed end-to-end.
- Manual: `docker compose up -d`, confirm `cognee-db` healthcheck passes, run the
  backend with `COGNEE_MODE=local`, exercise a debate turn through the API, confirm a
  row lands in the `cognee-db` Postgres instance.
