# Configurable local/cloud Cognee backend — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `debatemind-backend`'s Cognee integration switch between a self-hosted local backend (Postgres+pgvector+Kuzu, always running via `docker-compose.yml`) and the existing cloud-oriented config, via a `COGNEE_MODE` env var — and fix the pre-existing bug where `cognee_svc.py` calls SDK methods that don't exist.

**Architecture:** `cognee_svc.py` keeps calling the `cognee` Python SDK in-process (no architecture change there), but is fixed to use the SDK's real API (`add`/`cognify`/`search`) instead of the nonexistent `remember`/`recall`/`improve`. A new `cognee_config.py` module holds a single `configure_cognee(settings)` function that branches on `settings.cognee_mode` to either point cognee's relational/vector/graph config at the new `cognee-db` Postgres+pgvector container (local) or leave storage at cognee's defaults and only set the LLM key (cloud, today's exact behavior). `main.py`'s lifespan calls this one function instead of inlining the config logic.

**Tech Stack:** Python 3.11, FastAPI, `cognee==0.1.40` (extras: `postgres`, `kuzu`), pytest + `pytest-asyncio` (auto mode), Docker Compose, `pgvector/pgvector:pg16` image.

## Global Constraints

- `cognee==0.1.40` is pinned — all SDK usage in this plan is verified against the actual installed package source (`debatemind-backend/.venv/lib/python3.12/site-packages/cognee/`), not newer upstream docs.
- `cognee.config.set_relational_db_config` / `set_vector_db_config` / `set_graph_db_config` / `set_llm_config` validate every dict key with `hasattr()` against the underlying pydantic config object and raise on unknown keys — only use the exact field names verified in the spec.
- `COGNEE_MODE` defaults to `"local"` so a fresh `.env` works out of the box without a Cognee Cloud account.
- The `cognee-db` Docker Compose service must always be defined (not profile-gated) so flipping `COGNEE_MODE` never requires editing `docker-compose.yml`.
- Existing cloud-mode behavior (the `if settings.cognee_api_key and settings.cognee_llm_api_key: cognee.config.set_llm_config(...)` block currently in `main.py`) must be preserved byte-for-byte, just relocated.
- `recall_weaknesses` must keep returning `list[dict]` shaped as `[{"text": ...}, ...]` — `opponent.py:21` and `graph_svc.py:13` depend on this exact shape.
- This repo's pytest config has `asyncio_mode = "auto"` (`pyproject.toml:57`) — async test functions need no `@pytest.mark.asyncio` decorator.
- `tests/conftest.py` sets `DATABASE_URL`, `SECRET_KEY`, `OPENROUTER_API_KEY` via `os.environ.setdefault` so `debatemind.config.settings` can be imported without a `.env` file — new required-looking fields must have defaults so this keeps working.

---

### Task 1: Add local-mode Cognee dependencies

**Files:**
- Modify: `debatemind-backend/pyproject.toml:18`

**Interfaces:**
- Produces: `psycopg2`, `pgvector`, `kuzu` importable in the backend's venv (consumed at runtime by cognee's pgvector/kuzu adapters in Task 5's local-mode config).

- [ ] **Step 1: Change the cognee dependency line to include extras**

In `debatemind-backend/pyproject.toml`, change:

```toml
    "cognee==0.1.40",
```

to:

```toml
    "cognee[postgres,kuzu]==0.1.40",
```

- [ ] **Step 2: Sync the environment**

Run: `cd debatemind-backend && uv sync`

Expected: completes without error; output mentions installing `psycopg2-binary` (or `psycopg2`), `pgvector`, and `kuzu`.

- [ ] **Step 3: Verify the new packages import**

Run: `cd debatemind-backend && uv run python -c "import psycopg2, pgvector, kuzu; print('ok')"`

Expected: prints `ok` with no `ModuleNotFoundError`.

- [ ] **Step 4: Commit**

```bash
cd /Volumes/External/hackathon
git add debatemind-backend/pyproject.toml debatemind-backend/uv.lock
git commit -m "build: add postgres/kuzu extras to cognee dependency"
```

(If `uv.lock` wasn't modified/tracked, omit it from the `git add`.)

---

### Task 2: Add the `cognee-db` service to docker-compose.yml

**Files:**
- Modify: `docker-compose.yml`

**Interfaces:**
- Produces: a Postgres+pgvector instance reachable at `localhost:5433` (user `cognee`, password `cognee`, database `cognee`) whenever `docker compose up -d` runs — consumed by Task 5's local-mode `cognee_config.py` connection settings.

- [ ] **Step 1: Add the `cognee-db` service and its volume**

Current `docker-compose.yml`:

```yaml
services:
  db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: debatemind
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5437:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 10

volumes:
  pgdata:
```

Replace with:

```yaml
services:
  db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: debatemind
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5437:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 10

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

volumes:
  pgdata:
  cognee_pgdata:
```

- [ ] **Step 2: Validate the compose file**

Run: `docker compose config --quiet`

Expected: no output, exit code 0 (confirms valid YAML/schema).

- [ ] **Step 3: Start it and confirm the healthcheck passes**

Run: `docker compose up -d cognee-db && sleep 3 && docker compose ps cognee-db`

Expected: `STATUS` column shows `Up ... (healthy)`.

- [ ] **Step 4: Commit**

```bash
cd /Volumes/External/hackathon
git add docker-compose.yml
git commit -m "feat: add self-hosted pgvector service for local Cognee mode"
```

---

### Task 3: Fix `cognee_svc.py` to use the real cognee SDK API

**Files:**
- Modify: `debatemind-backend/debatemind/services/cognee_svc.py`
- Test: `debatemind-backend/tests/test_cognee_svc.py` (create)

**Interfaces:**
- Consumes: `cognee.add(data, dataset_name=str)`, `cognee.cognify(datasets=str)`, `cognee.search(query_text=str, query_type=SearchType, datasets=list[str], top_k=int)` — real SDK functions, verified against `debatemind-backend/.venv/lib/python3.12/site-packages/cognee/__init__.py` and `.../api/v1/{add,cognify,search}/*.py`.
- Produces (unchanged signatures, consumed by `pipeline.py`, `opponent.py`, `graph_svc.py`, `routers/sessions.py`):
  - `async def remember_argument(user_id, session_id, topic, claim_text, pattern_type, fallacy, evidence_quality, outcome) -> None`
  - `async def recall_weaknesses(user_id) -> list[dict]` — each dict shaped `{"text": str}`
  - `async def improve_fingerprint(user_id, session_id) -> None`
  - `async def forget_pattern(user_id, pattern_type) -> None`

- [ ] **Step 1: Write the failing tests**

Create `debatemind-backend/tests/test_cognee_svc.py`:

```python
"""
Unit tests for cognee_svc — verifies the service calls the real cognee SDK API
(add/cognify/search), not the nonexistent remember/recall/improve methods.
cognee.* calls are mocked; no real cognee storage/LLM calls happen here.
"""

from unittest.mock import AsyncMock

from debatemind.services import cognee_svc


async def test_remember_argument_adds_then_cognifies_the_dataset(monkeypatch):
    add_mock = AsyncMock()
    cognify_mock = AsyncMock()
    monkeypatch.setattr(cognee_svc.cognee, "add", add_mock)
    monkeypatch.setattr(cognee_svc.cognee, "cognify", cognify_mock)

    await cognee_svc.remember_argument(
        user_id="u1",
        session_id="s1",
        topic="AI Safety",
        claim_text="AI will inevitably take over",
        pattern_type="SlipperySlope",
        fallacy="SlipperySlope",
        evidence_quality="Weak",
        outcome="Lost",
    )

    add_mock.assert_awaited_once()
    text_arg, kwargs = add_mock.call_args.args[0], add_mock.call_args.kwargs
    assert kwargs["dataset_name"] == "user_u1_fingerprint"
    assert "AI will inevitably take over" in text_arg
    assert "SlipperySlope" in text_arg

    cognify_mock.assert_awaited_once_with(datasets="user_u1_fingerprint")


async def test_recall_weaknesses_searches_and_wraps_results_as_text_dicts(monkeypatch):
    search_mock = AsyncMock(return_value=["StrawMan pattern found", "AdHominem pattern found"])
    monkeypatch.setattr(cognee_svc.cognee, "search", search_mock)

    results = await cognee_svc.recall_weaknesses("u1")

    search_mock.assert_awaited_once()
    kwargs = search_mock.call_args.kwargs
    assert kwargs["query_type"] == cognee_svc.SearchType.GRAPH_COMPLETION
    assert kwargs["datasets"] == ["user_u1_fingerprint"]
    assert kwargs["top_k"] == 10
    assert "u1" in kwargs["query_text"]

    assert results == [
        {"text": "StrawMan pattern found"},
        {"text": "AdHominem pattern found"},
    ]


async def test_improve_fingerprint_recognifies_the_dataset(monkeypatch):
    cognify_mock = AsyncMock()
    monkeypatch.setattr(cognee_svc.cognee, "cognify", cognify_mock)

    await cognee_svc.improve_fingerprint("u1", "s1")

    cognify_mock.assert_awaited_once_with(datasets="user_u1_fingerprint")


async def test_forget_pattern_records_a_mastered_marker(monkeypatch):
    add_mock = AsyncMock()
    cognify_mock = AsyncMock()
    monkeypatch.setattr(cognee_svc.cognee, "add", add_mock)
    monkeypatch.setattr(cognee_svc.cognee, "cognify", cognify_mock)

    await cognee_svc.forget_pattern("u1", "StrawMan")

    add_mock.assert_awaited_once()
    text_arg, kwargs = add_mock.call_args.args[0], add_mock.call_args.kwargs
    assert kwargs["dataset_name"] == "user_u1_fingerprint"
    assert "MASTERED" in text_arg
    assert "StrawMan" in text_arg

    cognify_mock.assert_awaited_once_with(datasets="user_u1_fingerprint")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd debatemind-backend && uv run pytest tests/test_cognee_svc.py -v`

Expected: all 4 tests FAIL — `AttributeError: <module 'cognee'> does not have the attribute 'add'` will NOT be the error (cognee.add exists); instead they'll fail because `cognee_svc.remember_argument` etc. still call `cognee.remember`/`cognee.recall`/`cognee.improve`, so `add_mock`/`cognify_mock`/`search_mock` are never called and the `assert_awaited_once()` calls fail, or an `AttributeError` is raised trying to call the real (nonexistent) `cognee.remember`.

- [ ] **Step 3: Rewrite `cognee_svc.py` to use the real API**

Replace the full contents of `debatemind-backend/debatemind/services/cognee_svc.py`:

```python
import cognee
from cognee.api.v1.search.search import SearchType


def _dataset(user_id: str) -> str:
    return f"user_{user_id}_fingerprint"


async def remember_argument(
    user_id: str,
    session_id: str,
    topic: str,
    claim_text: str,
    pattern_type: str,
    fallacy: str | None,
    evidence_quality: str,
    outcome: str,
) -> None:
    text = (
        f"User: {user_id}\n"
        f"Session: {session_id}\n"
        f"Topic: {topic}\n"
        f"Claim: {claim_text}\n"
        f"ArgumentPattern: {pattern_type}\n"
        f"Fallacy: {fallacy or 'None'}\n"
        f"Evidence: {evidence_quality}\n"
        f"Outcome: {outcome}\n"
    )
    dataset = _dataset(user_id)
    await cognee.add(text, dataset_name=dataset)
    await cognee.cognify(datasets=dataset)


async def recall_weaknesses(user_id: str) -> list[dict]:
    results = await cognee.search(
        query_text=f"top weakness patterns and fallacies for user {user_id}",
        query_type=SearchType.GRAPH_COMPLETION,
        datasets=[_dataset(user_id)],
        top_k=10,
    )
    return [{"text": r if isinstance(r, str) else getattr(r, "text", str(r))} for r in results]


async def improve_fingerprint(user_id: str, session_id: str) -> None:
    # cognee 0.1.40 has no separate "improve" step; re-cognifying the dataset
    # incorporates anything added since the last cognify call.
    await cognee.cognify(datasets=_dataset(user_id))


async def forget_pattern(user_id: str, pattern_type: str) -> None:
    # cognee has no forget primitive; mark the pattern as mastered so the
    # opponent stops targeting it.
    dataset = _dataset(user_id)
    text = (
        f"User: {user_id}\nPattern: {pattern_type}\n"
        "Status: MASTERED\nAction: prune from opponent strategy"
    )
    await cognee.add(text, dataset_name=dataset)
    await cognee.cognify(datasets=dataset)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd debatemind-backend && uv run pytest tests/test_cognee_svc.py -v`

Expected: all 4 tests PASS.

- [ ] **Step 5: Run the full test suite to confirm no regressions**

Run: `cd debatemind-backend && uv run pytest -v`

Expected: all tests (including `test_mastery.py`, `test_prompts.py`) PASS.

- [ ] **Step 6: Commit**

```bash
cd /Volumes/External/hackathon
git add debatemind-backend/debatemind/services/cognee_svc.py debatemind-backend/tests/test_cognee_svc.py
git commit -m "fix: use real cognee SDK API (add/cognify/search) instead of nonexistent remember/recall/improve"
```

---

### Task 4: Add `COGNEE_MODE` and local-mode connection settings

**Files:**
- Modify: `debatemind-backend/debatemind/config.py`
- Modify: `debatemind-backend/.env.example`
- Test: `debatemind-backend/tests/test_config.py` (create)

**Interfaces:**
- Produces: `Settings.cognee_mode: str` (default `"local"`), `Settings.cognee_db_host: str`, `Settings.cognee_db_port: str`, `Settings.cognee_db_name: str`, `Settings.cognee_db_username: str`, `Settings.cognee_db_password: str` — consumed by `cognee_config.py` in Task 5.

- [ ] **Step 1: Write the failing test**

Create `debatemind-backend/tests/test_config.py`:

```python
"""Verifies Settings exposes the Cognee local/cloud mode switch with safe defaults."""

from debatemind.config import Settings


def test_cognee_mode_defaults_to_local():
    settings = Settings(
        database_url="sqlite+aiosqlite:///./test.db",
        secret_key="test-secret-key-at-least-32-characters!",
        openrouter_api_key="test-key",
    )
    assert settings.cognee_mode == "local"
    assert settings.cognee_db_host == "localhost"
    assert settings.cognee_db_port == "5433"
    assert settings.cognee_db_name == "cognee"
    assert settings.cognee_db_username == "cognee"
    assert settings.cognee_db_password == "cognee"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd debatemind-backend && uv run pytest tests/test_config.py -v`

Expected: FAIL with `TypeError: ... extra fields not permitted` or `AttributeError: 'Settings' object has no attribute 'cognee_mode'` (field doesn't exist yet).

- [ ] **Step 3: Add the fields to `Settings`**

In `debatemind-backend/debatemind/config.py`, change:

```python
    cognee_api_key: str = ""
    cognee_llm_api_key: str = ""
```

to:

```python
    cognee_mode: str = "local"  # "local" (self-hosted via docker-compose) | "cloud"
    cognee_api_key: str = ""
    cognee_llm_api_key: str = ""
    cognee_db_host: str = "localhost"
    cognee_db_port: str = "5433"
    cognee_db_name: str = "cognee"
    cognee_db_username: str = "cognee"
    cognee_db_password: str = "cognee"
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd debatemind-backend && uv run pytest tests/test_config.py -v`

Expected: PASS.

- [ ] **Step 5: Update `.env.example`**

Current `debatemind-backend/.env.example`:

```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/debatemind
SECRET_KEY=change-me-32-chars-minimum
ANTHROPIC_API_KEY=sk-ant-...
COGNEE_API_KEY=your-cognee-api-key
COGNEE_LLM_API_KEY=sk-ant-...
```

Replace with:

```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5437/debatemind
SECRET_KEY=change-me-32-chars-minimum
ANTHROPIC_API_KEY=sk-ant-...

# Cognee backend mode: "local" (default, self-hosted via the cognee-db service
# in docker-compose.yml) or "cloud" (Cognee Cloud's hosted API).
COGNEE_MODE=local
# Anthropic key cognee uses for its own LLM calls — required in both modes.
COGNEE_LLM_API_KEY=sk-ant-...
# Only used when COGNEE_MODE=cloud.
COGNEE_API_KEY=your-cognee-api-key

# Only relevant when COGNEE_MODE=local — defaults already match the cognee-db
# service in docker-compose.yml, override only if you changed that service.
# COGNEE_DB_HOST=localhost
# COGNEE_DB_PORT=5433
# COGNEE_DB_NAME=cognee
# COGNEE_DB_USERNAME=cognee
# COGNEE_DB_PASSWORD=cognee
```

- [ ] **Step 6: Commit**

```bash
cd /Volumes/External/hackathon
git add debatemind-backend/debatemind/config.py debatemind-backend/.env.example debatemind-backend/tests/test_config.py
git commit -m "feat: add COGNEE_MODE setting with local/cloud connection config"
```

---

### Task 5: Wire `COGNEE_MODE` into cognee's runtime config

**Files:**
- Create: `debatemind-backend/debatemind/services/cognee_config.py`
- Modify: `debatemind-backend/debatemind/main.py`
- Test: `debatemind-backend/tests/test_cognee_config.py` (create)

**Interfaces:**
- Consumes: `Settings` (from Task 4) — `cognee_mode`, `cognee_db_host`, `cognee_db_port`, `cognee_db_name`, `cognee_db_username`, `cognee_db_password`, `cognee_api_key`, `cognee_llm_api_key`.
- Consumes: `cognee.config.set_relational_db_config(dict)`, `set_vector_db_config(dict)`, `set_graph_db_config(dict)`, `set_llm_config(dict)` — verified real methods on `debatemind-backend/.venv/lib/python3.12/site-packages/cognee/api/v1/config/config.py`.
- Produces: `def configure_cognee(settings: Settings) -> None` — called once from `main.py`'s lifespan.

- [ ] **Step 1: Write the failing tests**

Create `debatemind-backend/tests/test_cognee_config.py`:

```python
"""
Unit tests for cognee_config.configure_cognee — verifies the local/cloud mode
switch calls the right cognee.config.set_* methods with the right dict keys.
All cognee.config.set_* calls are mocked; nothing touches a real database.
"""

from unittest.mock import MagicMock

from debatemind.config import Settings
from debatemind.services import cognee_config


def _settings(**overrides) -> Settings:
    base = dict(
        database_url="sqlite+aiosqlite:///./test.db",
        secret_key="test-secret-key-at-least-32-characters!",
        openrouter_api_key="test-key",
        cognee_mode="local",
        cognee_api_key="",
        cognee_llm_api_key="llm-key",
        cognee_db_host="localhost",
        cognee_db_port="5433",
        cognee_db_name="cognee",
        cognee_db_username="cognee",
        cognee_db_password="cognee",
    )
    base.update(overrides)
    return Settings(**base)


def _patch_cognee_config(monkeypatch):
    mocks = {
        "relational": MagicMock(),
        "vector": MagicMock(),
        "graph": MagicMock(),
        "llm": MagicMock(),
    }
    monkeypatch.setattr(
        cognee_config.cognee.config, "set_relational_db_config", mocks["relational"]
    )
    monkeypatch.setattr(cognee_config.cognee.config, "set_vector_db_config", mocks["vector"])
    monkeypatch.setattr(cognee_config.cognee.config, "set_graph_db_config", mocks["graph"])
    monkeypatch.setattr(cognee_config.cognee.config, "set_llm_config", mocks["llm"])
    return mocks


def test_local_mode_configures_postgres_pgvector_kuzu_and_llm(monkeypatch):
    mocks = _patch_cognee_config(monkeypatch)

    cognee_config.configure_cognee(_settings(cognee_mode="local"))

    mocks["relational"].assert_called_once_with(
        {
            "db_provider": "postgres",
            "db_host": "localhost",
            "db_port": "5433",
            "db_name": "cognee",
            "db_username": "cognee",
            "db_password": "cognee",
        }
    )
    mocks["vector"].assert_called_once_with({"vector_db_provider": "pgvector"})
    mocks["graph"].assert_called_once_with({"graph_database_provider": "kuzu"})
    mocks["llm"].assert_called_once()
    assert mocks["llm"].call_args.args[0]["api_key"] == "llm-key"


def test_local_mode_skips_llm_config_without_a_key(monkeypatch):
    mocks = _patch_cognee_config(monkeypatch)

    cognee_config.configure_cognee(_settings(cognee_mode="local", cognee_llm_api_key=""))

    mocks["llm"].assert_not_called()


def test_cloud_mode_does_not_touch_local_db_config(monkeypatch):
    mocks = _patch_cognee_config(monkeypatch)

    cognee_config.configure_cognee(
        _settings(cognee_mode="cloud", cognee_api_key="cloud-key", cognee_llm_api_key="llm-key")
    )

    mocks["relational"].assert_not_called()
    mocks["vector"].assert_not_called()
    mocks["graph"].assert_not_called()
    mocks["llm"].assert_called_once()


def test_cloud_mode_without_both_keys_skips_llm_config(monkeypatch):
    mocks = _patch_cognee_config(monkeypatch)

    cognee_config.configure_cognee(
        _settings(cognee_mode="cloud", cognee_api_key="", cognee_llm_api_key="llm-key")
    )

    mocks["llm"].assert_not_called()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd debatemind-backend && uv run pytest tests/test_cognee_config.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'debatemind.services.cognee_config'`.

- [ ] **Step 3: Create `cognee_config.py`**

Create `debatemind-backend/debatemind/services/cognee_config.py`:

```python
import cognee

from debatemind.config import Settings

LLM_MODEL = "claude-haiku-4-5-20251001"


def configure_cognee(settings: Settings) -> None:
    if settings.cognee_mode == "local":
        cognee.config.set_relational_db_config(
            {
                "db_provider": "postgres",
                "db_host": settings.cognee_db_host,
                "db_port": settings.cognee_db_port,
                "db_name": settings.cognee_db_name,
                "db_username": settings.cognee_db_username,
                "db_password": settings.cognee_db_password,
            }
        )
        cognee.config.set_vector_db_config({"vector_db_provider": "pgvector"})
        cognee.config.set_graph_db_config({"graph_database_provider": "kuzu"})
        if settings.cognee_llm_api_key:
            cognee.config.set_llm_config(
                {
                    "provider": "anthropic",
                    "model": LLM_MODEL,
                    "api_key": settings.cognee_llm_api_key,
                }
            )
    elif settings.cognee_mode == "cloud":
        if settings.cognee_api_key and settings.cognee_llm_api_key:
            cognee.config.set_llm_config(
                {
                    "provider": "anthropic",
                    "model": LLM_MODEL,
                    "api_key": settings.cognee_llm_api_key,
                }
            )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd debatemind-backend && uv run pytest tests/test_cognee_config.py -v`

Expected: all 4 tests PASS.

- [ ] **Step 5: Wire it into `main.py`**

Current `debatemind-backend/debatemind/main.py`:

```python
import logging
from contextlib import asynccontextmanager

import cognee
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from debatemind.config import settings
from debatemind.database import Base, engine
from debatemind.models import mastery, session, user  # noqa: F401
from debatemind.routers import auth, sessions, topics, users

logger = logging.getLogger("debatemind")


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:  # noqa: BLE001
        logger.warning("DB not reachable at startup: %s", exc)

    if settings.cognee_api_key and settings.cognee_llm_api_key:
        cognee.config.set_llm_config(
            {
                "provider": "anthropic",
                "model": "claude-haiku-4-5-20251001",
                "api_key": settings.cognee_llm_api_key,
            }
        )

    yield
```

Replace the `import cognee` line and the lifespan's cognee block:

```python
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from debatemind.config import settings
from debatemind.database import Base, engine
from debatemind.models import mastery, session, user  # noqa: F401
from debatemind.routers import auth, sessions, topics, users
from debatemind.services.cognee_config import configure_cognee

logger = logging.getLogger("debatemind")


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:  # noqa: BLE001
        logger.warning("DB not reachable at startup: %s", exc)

    configure_cognee(settings)

    yield
```

(The rest of `main.py` — `app = FastAPI(...)`, middleware, routers, `/health` — is unchanged.)

- [ ] **Step 6: Run the full test suite**

Run: `cd debatemind-backend && uv run pytest -v`

Expected: all tests PASS, including `test_cognee_svc.py`, `test_config.py`, `test_cognee_config.py`, `test_mastery.py`, `test_prompts.py`.

- [ ] **Step 7: Run ruff to confirm no lint errors from the unused `cognee` import removal**

Run: `cd debatemind-backend && uv run ruff check debatemind/main.py debatemind/services/cognee_config.py`

Expected: no errors.

- [ ] **Step 8: Commit**

```bash
cd /Volumes/External/hackathon
git add debatemind-backend/debatemind/main.py debatemind-backend/debatemind/services/cognee_config.py debatemind-backend/tests/test_cognee_config.py
git commit -m "feat: switch Cognee storage backend via COGNEE_MODE (local pgvector+kuzu vs cloud)"
```

---

### Task 6: Update README and verify end-to-end

**Files:**
- Modify: `README.md`

**Interfaces:**
- None (documentation + manual verification only).

- [ ] **Step 1: Update the backend env var block in `README.md`**

Current (`README.md:85-93`):

```
### Backend (`debatemind-backend/.env`)
```
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/debatemind
SECRET_KEY=<random-secret>
OPENROUTER_API_KEY=<your-openrouter-key>
# Optional: override default models (any OpenRouter slug works)
# FAST_MODEL=google/gemini-flash-1.5
# MAIN_MODEL=meta-llama/llama-3.1-70b-instruct
```
```

Replace with:

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
```

- [ ] **Step 2: Commit the README change**

```bash
cd /Volumes/External/hackathon
git add README.md
git commit -m "docs: document COGNEE_MODE and local Cognee setup"
```

- [ ] **Step 3: Manual end-to-end verification**

Run:

```bash
cd /Volumes/External/hackathon
docker compose up -d
until docker compose exec cognee-db pg_isready -U cognee -q; do sleep 1; done
echo "cognee-db ready"
cd debatemind-backend
cp .env.example .env   # then fill in SECRET_KEY, OPENROUTER_API_KEY, ANTHROPIC_API_KEY, COGNEE_LLM_API_KEY
uv run uvicorn debatemind.main:app --port 8001 &
sleep 2
curl -s http://localhost:8001/health
```

Expected: `{"status":"ok"}`. Check the uvicorn log output for no `AttributeError` or
`InvalidAttributeError` from cognee during startup. Then exercise a debate turn
through the API (or the frontend) and confirm a `user_<id>_fingerprint` dataset's
data lands in the `cognee` database on `localhost:5433` (e.g.
`docker compose exec cognee-db psql -U cognee -d cognee -c '\dt'` should list
tables after the first turn completes).

Stop the backend process (`kill %1` or Ctrl+C) when done.

---

## Self-Review Notes

- **Spec coverage:** Task 1 covers spec §5 (pyproject extras). Task 2 covers spec §4
  (docker-compose). Task 3 covers spec §1 (cognee_svc.py fix). Task 4 covers spec §2
  (config). Task 5 covers spec §3 (main.py wiring, extracted into `cognee_config.py`
  per the writing-plans "design for isolation" guidance so it's unit-testable without
  booting FastAPI). Task 6 covers documentation and the spec's manual testing section.
- **Placeholder scan:** no TBD/TODO; every step has complete, runnable code.
- **Type consistency:** `configure_cognee(settings: Settings) -> None` signature is
  identical between Task 5's test imports, implementation, and `main.py`'s call site.
  `_dataset(user_id)` format (`user_{user_id}_fingerprint`) is identical across all four
  `cognee_svc.py` functions and matches the existing dataset naming convention noted in
  the original plan doc (`docs/superpowers/plans/2026-06-29-debatemind.md:16`).
