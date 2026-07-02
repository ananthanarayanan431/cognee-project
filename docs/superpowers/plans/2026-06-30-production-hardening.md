# Production Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make DebateMind production-ready by replacing synchronous Cognee PDF indexing with a Celery+Redis async worker, fixing a memory leak in the weakness cache, adding request timeouts, and adding structured JSON logging via structlog.

**Architecture:** A Redis broker handles the task queue; a Celery worker process runs `index_source_task` in the background (asyncio.run inside the synchronous Celery task). The FastAPI upload endpoint returns 202 immediately; the frontend polls `GET /source-status` every 2 s until the Celery worker marks the session `source_status="indexed"`. Structured JSON logs (structlog) replace ad-hoc string logs throughout the service.

**Tech Stack:** Celery 5.4 + Redis 7, structlog 24, cachetools 5.5, httpx.Timeout on the OpenRouter client, asyncio.wait_for on Cognee SDK calls.

## Global Constraints

- Python ≥ 3.11, uv for dependency management (run all Python commands as `uv run …`)
- Package manager: `uv add` to add dependencies (updates pyproject.toml + uv.lock)
- DB: SQLite (aiosqlite) in tests, Postgres (asyncpg) in production — use only SQLAlchemy ORM/Core, no raw SQL
- All new async tests use pytest-asyncio auto mode (already configured in pyproject.toml)
- Celery broker + backend URL: `settings.redis_url` (format: `redis://localhost:6379/0`)
- New `source_status` column values: exactly `"none"` | `"pending"` | `"indexed"` | `"failed"`
- Structlog JSON output: one JSON object per line to stdout; processors listed in Task 6
- OpenRouter timeout: `httpx.Timeout(30.0, connect=5.0)` — do not use a single positional float
- Cognee `add` timeout: 60 s; Cognee `cognify` timeout: 300 s; `recall_source_context` search timeout: 10 s
- weakness cache: `cachetools.TTLCache(maxsize=1024, ttl=3600)` — no asyncio.Lock needed (single async event loop)
- Do not add Alembic migrations — the app uses `Base.metadata.create_all` at startup
- Commit frequently; each task is one or two commits maximum
- ruff lint must pass: `cd debatemind-backend && uv run ruff check .`

---

## File Map

**Created:**
- `debatemind-backend/debatemind/worker/__init__.py`
- `debatemind-backend/debatemind/worker/celery_app.py`
- `debatemind-backend/debatemind/worker/tasks.py`
- `debatemind-backend/debatemind/middleware.py`
- `debatemind-backend/tests/test_worker_tasks.py`

**Modified:**
- `docker-compose.yml` — add Redis service
- `debatemind-backend/pyproject.toml` — add celery, redis, structlog, cachetools deps
- `debatemind-backend/debatemind/config.py` — add `redis_url`
- `debatemind-backend/debatemind/models/session.py` — add `source_status` column
- `debatemind-backend/debatemind/schemas/session.py` — add `SourceStatusOut`, update `SessionOut`
- `debatemind-backend/debatemind/services/cognee_svc.py` — loud logging + asyncio timeouts
- `debatemind-backend/debatemind/agents/opponent.py` — TTLCache for `_weakness_cache`
- `debatemind-backend/debatemind/agents/client.py` — httpx.Timeout on OpenRouter
- `debatemind-backend/debatemind/routers/sessions.py` — async upload, source-status endpoint
- `debatemind-backend/debatemind/main.py` — structlog setup, RequestIDMiddleware
- `debatemind-backend/tests/test_sessions_router.py` — update for async upload + new endpoint
- `debatemind-backend/tests/test_cognee_svc.py` — update for timeout wrappers
- `Makefile` — add celery target, update dev
- `frontend/src/lib/api.ts` — add `getSourceStatus`
- `frontend/src/components/topic/TopicSelection.tsx` — polling + "Start anyway" button

---

### Task 1: Infra, dependencies, and Makefile

**Files:**
- Modify: `docker-compose.yml`
- Modify: `debatemind-backend/pyproject.toml`
- Modify: `debatemind-backend/debatemind/config.py`
- Modify: `Makefile`

**Interfaces:**
- Produces: `settings.redis_url: str` consumed by Tasks 3 and 4
- Produces: `celery`, `redis`, `structlog`, `cachetools` packages available to all later tasks

- [ ] **Step 1: Add Redis to docker-compose.yml**

Add this service block after the `minio` service (before `volumes:`):

```yaml
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 10
```

- [ ] **Step 2: Add Python dependencies**

```bash
cd debatemind-backend
uv add "celery[redis]>=5.4" "redis>=5.0" "structlog>=24.0" "cachetools>=5.5"
```

Expected: pyproject.toml and uv.lock are updated; no error output.

- [ ] **Step 3: Add redis_url to config.py**

Add this line to the `Settings` class in `debatemind-backend/debatemind/config.py`, after `minio_secure`:

```python
    redis_url: str = "redis://localhost:6379/0"
```

- [ ] **Step 4: Update Makefile**

Replace the entire Makefile content:

```makefile
.PHONY: debatemind-backend frontend celery dev infra-up infra-down infra-build infra-logs start

debatemind-backend:
	cd debatemind-backend && uv run uvicorn debatemind.main:app --reload --port 8001

frontend:
	cd frontend && npm run dev

celery:
	cd debatemind-backend && uv run celery -A debatemind.worker.celery_app worker --loglevel=info --concurrency=2

dev:
	make -j3 debatemind-backend frontend celery

# Infra: postgres, cognee-db (pgvector+kuzu), minio, redis
infra-build:
	docker compose build

infra-up:
	docker compose up -d --remove-orphans

infra-down:
	docker compose down --remove-orphans

infra-logs:
	docker compose logs -f

# Start everything: infra first, then backend + frontend + celery in parallel
start:
	make infra-up && make dev
```

- [ ] **Step 5: Write the failing test**

Create `debatemind-backend/tests/test_config.py` already exists — verify it has a test for `redis_url`. If not, add one:

```python
# Append to debatemind-backend/tests/test_config.py
def test_redis_url_has_default():
    from debatemind.config import settings
    assert settings.redis_url.startswith("redis://")
```

Run: `cd debatemind-backend && uv run pytest tests/test_config.py -v`
Expected: PASS (or already passing if test_config.py already covers redis_url).

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml debatemind-backend/pyproject.toml debatemind-backend/uv.lock debatemind-backend/debatemind/config.py Makefile debatemind-backend/tests/test_config.py
git commit -m "feat: add Redis infra, Celery/structlog/cachetools deps, redis_url config"
```

---

### Task 2: Add source_status column and update schemas

**Files:**
- Modify: `debatemind-backend/debatemind/models/session.py`
- Modify: `debatemind-backend/debatemind/schemas/session.py`
- Test: `debatemind-backend/tests/test_session_model.py`

**Interfaces:**
- Produces: `DebateSession.source_status: Mapped[str]` — default `"none"`, consumed by Tasks 3 and 4
- Produces: `SourceStatusOut(source_status: str)` — consumed by Task 4
- Produces: `SessionOut.source_status: str` — consumed by Task 7 (frontend)

- [ ] **Step 1: Write the failing tests**

In `debatemind-backend/tests/test_session_model.py`, add at the end:

```python
async def test_source_status_defaults_to_none():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from debatemind.database import Base
    from debatemind.models.session import DebateSession

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as db:
        session = DebateSession(user_id="u1", topic="AI Safety")
        db.add(session)
        await db.commit()
        await db.refresh(session)
        assert session.source_status == "none"

    await engine.dispose()
```

Run: `cd debatemind-backend && uv run pytest tests/test_session_model.py -v`
Expected: FAIL with `AttributeError: 'DebateSession' object has no attribute 'source_status'`

- [ ] **Step 2: Add source_status column to the model**

In `debatemind-backend/debatemind/models/session.py`, add this line after `source_object_key`:

```python
    source_status: Mapped[str] = mapped_column(String, default="none", nullable=False)
```

The updated `DebateSession` block (relevant lines only):

```python
    source_filename: Mapped[str] = mapped_column(String, nullable=True)
    source_object_key: Mapped[str] = mapped_column(String, nullable=True)
    source_status: Mapped[str] = mapped_column(String, default="none", nullable=False)
```

- [ ] **Step 3: Add SourceStatusOut and update SessionOut in schemas**

Replace `debatemind-backend/debatemind/schemas/session.py` with:

```python
from typing import Optional

from pydantic import BaseModel


class SessionStartIn(BaseModel):
    topic: str
    description: str = ""
    difficulty: str = "targeted"
    user_position: str = "against"


class SessionOut(BaseModel):
    session_id: str
    topic: str
    description: str
    difficulty: str
    has_source: bool = False
    source_status: str = "none"


class SourceUploadOut(BaseModel):
    status: str
    source_filename: str


class SourceStatusOut(BaseModel):
    source_status: str


class SourceUrlOut(BaseModel):
    url: str


class MessageIn(BaseModel):
    text: str


class JudgeScores(BaseModel):
    logic: float
    evidence: float
    rhetoric: float
    fallacy: Optional[str]
    outcome: str
```

- [ ] **Step 4: Run tests**

Run: `cd debatemind-backend && uv run pytest tests/test_session_model.py -v`
Expected: PASS (all tests including new `test_source_status_defaults_to_none`)

Run the full suite to check for regressions: `cd debatemind-backend && uv run pytest -x -q`
Expected: all passing (the sessions router tests that check `source_object_key` directly against the DB still pass; `source_status` is a new column, not replacing anything yet).

- [ ] **Step 5: Commit**

```bash
git add debatemind-backend/debatemind/models/session.py debatemind-backend/debatemind/schemas/session.py debatemind-backend/tests/test_session_model.py
git commit -m "feat: add source_status column to DebateSession; SourceStatusOut schema"
```

---

### Task 3: Celery worker module

**Files:**
- Create: `debatemind-backend/debatemind/worker/__init__.py`
- Create: `debatemind-backend/debatemind/worker/celery_app.py`
- Create: `debatemind-backend/debatemind/worker/tasks.py`
- Create: `debatemind-backend/tests/test_worker_tasks.py`

**Interfaces:**
- Consumes: `settings.redis_url` (Task 1), `AsyncSessionLocal` from `debatemind.database`, `index_source_document` from `cognee_svc`, `download_to_tempfile` from `storage_svc`, `DebateSession` model (Task 2)
- Produces: `index_source_task` Celery task — signature `index_source_task(session_id: str, object_key: str) -> None` — consumed by Task 4

- [ ] **Step 1: Write the failing tests**

Create `debatemind-backend/tests/test_worker_tasks.py`:

```python
"""
Unit tests for the Celery indexing task.
All async helpers (_do_index, _set_status) are tested directly without
going through the Celery machinery so we don't need a running broker.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from debatemind.worker import tasks as worker_tasks


async def test_do_index_downloads_indexes_and_sets_status_indexed(monkeypatch, tmp_path):
    fake_tmp = tmp_path / "e.pdf"
    fake_tmp.write_bytes(b"pdf data")

    download_mock = MagicMock(return_value=fake_tmp)
    index_mock = AsyncMock()
    set_status_mock = AsyncMock()

    monkeypatch.setattr(worker_tasks.storage_svc, "download_to_tempfile", download_mock)
    monkeypatch.setattr(worker_tasks, "index_source_document", index_mock)
    monkeypatch.setattr(worker_tasks, "_set_status", set_status_mock)

    await worker_tasks._do_index("s1", "sources/s1/e.pdf")

    download_mock.assert_called_once_with("sources/s1/e.pdf")
    index_mock.assert_awaited_once_with("s1", str(fake_tmp))
    set_status_mock.assert_awaited_once_with("s1", "indexed")
    assert not fake_tmp.exists()


async def test_do_index_cleans_up_tempfile_even_when_indexing_fails(monkeypatch, tmp_path):
    fake_tmp = tmp_path / "e.pdf"
    fake_tmp.write_bytes(b"pdf data")

    monkeypatch.setattr(worker_tasks.storage_svc, "download_to_tempfile", MagicMock(return_value=fake_tmp))
    monkeypatch.setattr(worker_tasks, "index_source_document", AsyncMock(side_effect=RuntimeError("cognee down")))
    monkeypatch.setattr(worker_tasks, "_set_status", AsyncMock())

    with pytest.raises(RuntimeError, match="cognee down"):
        await worker_tasks._do_index("s1", "sources/s1/e.pdf")

    assert not fake_tmp.exists()


async def test_set_status_updates_db(monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy import select
    from debatemind.database import Base
    from debatemind.models.session import DebateSession

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as db:
        session = DebateSession(user_id="u1", topic="AI", source_status="pending")
        db.add(session)
        await db.commit()
        session_id = session.id

    # Patch AsyncSessionLocal to use the in-memory test engine
    monkeypatch.setattr(worker_tasks, "AsyncSessionLocal", factory)

    await worker_tasks._set_status(session_id, "indexed")

    async with factory() as db:
        result = await db.execute(select(DebateSession).where(DebateSession.id == session_id))
        s = result.scalar_one()
        assert s.source_status == "indexed"

    await engine.dispose()
```

Run: `cd debatemind-backend && uv run pytest tests/test_worker_tasks.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'debatemind.worker'`

- [ ] **Step 2: Create the worker package**

Create `debatemind-backend/debatemind/worker/__init__.py` (empty):
```python
```

- [ ] **Step 3: Create celery_app.py**

Create `debatemind-backend/debatemind/worker/celery_app.py`:

```python
from celery import Celery

from debatemind.config import settings

celery_app = Celery(
    "debatemind",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["debatemind.worker.tasks"],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)
```

- [ ] **Step 4: Create tasks.py**

Create `debatemind-backend/debatemind/worker/tasks.py`:

```python
import asyncio
import logging

from celery.signals import worker_init
from sqlalchemy import update

from debatemind.database import AsyncSessionLocal
from debatemind.models.session import DebateSession
from debatemind.services import storage_svc
from debatemind.services.cognee_svc import index_source_document
from debatemind.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@worker_init.connect
def _configure_cognee(**kwargs):
    from debatemind.config import settings
    from debatemind.services.cognee_config import configure_cognee

    configure_cognee(settings)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=30)
def index_source_task(self, session_id: str, object_key: str) -> None:
    try:
        asyncio.run(_do_index(session_id, object_key))
    except Exception as exc:
        logger.exception("index_source_task failed for session %s", session_id)
        asyncio.run(_set_status(session_id, "failed"))
        raise self.retry(exc=exc)


async def _do_index(session_id: str, object_key: str) -> None:
    tmp_path = storage_svc.download_to_tempfile(object_key)
    try:
        await index_source_document(session_id, str(tmp_path))
    finally:
        tmp_path.unlink(missing_ok=True)
    await _set_status(session_id, "indexed")


async def _set_status(session_id: str, status: str) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(DebateSession)
            .where(DebateSession.id == session_id)
            .values(source_status=status)
        )
        await db.commit()
```

- [ ] **Step 5: Run the tests**

Run: `cd debatemind-backend && uv run pytest tests/test_worker_tasks.py -v`
Expected: all 3 tests PASS.

Run ruff: `cd debatemind-backend && uv run ruff check debatemind/worker/`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add debatemind-backend/debatemind/worker/ debatemind-backend/tests/test_worker_tasks.py
git commit -m "feat: add Celery worker module with index_source_task"
```

---

### Task 4: Async upload endpoint + source-status endpoint

**Files:**
- Modify: `debatemind-backend/debatemind/routers/sessions.py`
- Modify: `debatemind-backend/tests/test_sessions_router.py`

**Interfaces:**
- Consumes: `index_source_task` from Task 3, `SourceStatusOut` from Task 2, `source_status` column from Task 2
- `POST /{session_id}/source` now returns HTTP 202 with `{"status": "pending", "source_filename": <name>}`
- New `GET /{session_id}/source-status` returns `{"source_status": "none"|"pending"|"indexed"|"failed"}`
- `send_message` uses `session.source_status == "indexed"` for `has_source` (was `bool(session.source_object_key)`)

- [ ] **Step 1: Update the import block in sessions.py**

Replace the import section at the top of `debatemind-backend/debatemind/routers/sessions.py`:

```python
import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func as sqlfunc
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from debatemind.agents.pipeline import debate_pipeline
from debatemind.agents.state import DebateState
from debatemind.database import get_db
from debatemind.deps import current_user_id
from debatemind.models.session import DebateSession, Exchange
from debatemind.schemas.session import (
    MessageIn,
    SessionOut,
    SessionStartIn,
    SourceStatusOut,
    SourceUploadOut,
    SourceUrlOut,
)
from debatemind.services import storage_svc
from debatemind.services.graph_svc import build_graph
from debatemind.worker.tasks import index_source_task
```

Note: `index_source_document` import is removed (now in the Celery task). `improve_fingerprint` is still used in `end_session` — add it back:

```python
from debatemind.services.cognee_svc import improve_fingerprint
```

- [ ] **Step 2: Rewrite the upload_source endpoint**

Replace the entire `upload_source` function in `sessions.py`:

```python
@router.post("/{session_id}/source", response_model=SourceUploadOut)
async def upload_source(
    session_id: str,
    file: UploadFile = File(...),
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
    response: Response = None,
):
    result = await db.execute(select(DebateSession).where(DebateSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session or session.user_id != user_id:
        raise HTTPException(status_code=404, detail="Session not found")

    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    data = await file.read()
    if len(data) > MAX_SOURCE_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 20MB limit")

    object_key = storage_svc.upload_source(session_id, file.filename, data)

    await db.execute(
        update(DebateSession)
        .where(DebateSession.id == session_id)
        .values(
            source_filename=file.filename,
            source_object_key=object_key,
            source_status="pending",
        )
    )
    await db.commit()

    index_source_task.delay(session_id, object_key)

    if response is not None:
        response.status_code = 202
    return SourceUploadOut(status="pending", source_filename=file.filename)
```

Note: FastAPI doesn't easily set a 202 status code via `response_model` alone. Use `JSONResponse` instead:

Actually, the cleanest approach is to return a `JSONResponse` directly:

```python
from fastapi.responses import JSONResponse, StreamingResponse

@router.post("/{session_id}/source")
async def upload_source(
    session_id: str,
    file: UploadFile = File(...),
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(DebateSession).where(DebateSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session or session.user_id != user_id:
        raise HTTPException(status_code=404, detail="Session not found")

    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    data = await file.read()
    if len(data) > MAX_SOURCE_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 20MB limit")

    object_key = storage_svc.upload_source(session_id, file.filename, data)

    await db.execute(
        update(DebateSession)
        .where(DebateSession.id == session_id)
        .values(
            source_filename=file.filename,
            source_object_key=object_key,
            source_status="pending",
        )
    )
    await db.commit()

    index_source_task.delay(session_id, object_key)

    return JSONResponse(
        status_code=202,
        content={"status": "pending", "source_filename": file.filename},
    )
```

Update the import for `JSONResponse` — add to the imports at the top:
```python
from fastapi.responses import JSONResponse, StreamingResponse
```
(Replace the existing `from fastapi.responses import StreamingResponse`)

- [ ] **Step 3: Add the source-status endpoint**

Add this function after the `upload_source` function:

```python
@router.get("/{session_id}/source-status", response_model=SourceStatusOut)
async def get_source_status(
    session_id: str,
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(DebateSession).where(DebateSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session or session.user_id != user_id:
        raise HTTPException(status_code=404, detail="Session not found")
    return SourceStatusOut(source_status=session.source_status)
```

- [ ] **Step 4: Update send_message to use source_status**

In the `send_message` function, change:
```python
        has_source=bool(session.source_object_key),
```
to:
```python
        has_source=(session.source_status == "indexed"),
```

- [ ] **Step 5: Update start_session to include source_status in the response**

In `start_session`, update the `SessionOut` return:
```python
    return SessionOut(
        session_id=session.id,
        topic=session.topic,
        description=session.description or "",
        difficulty=session.difficulty,
        has_source=False,
        source_status="none",
    )
```

- [ ] **Step 6: Write updated tests for the sessions router**

Replace the content of `debatemind-backend/tests/test_sessions_router.py`:

```python
"""
API-level tests for the sessions router's concept/source-upload endpoints.
storage_svc (MinIO) and Celery tasks are mocked so no real MinIO/Cognee/Redis
I/O happens; the DB layer is a real in-memory SQLite.
"""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from debatemind.database import Base, get_db
from debatemind.deps import current_user_id
from debatemind.models.session import DebateSession
from debatemind.routers import sessions as sessions_router
from debatemind.services import storage_svc


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def api_client(session_factory):
    async def override_get_db():
        async with session_factory() as session:
            yield session

    app = FastAPI()
    app.include_router(sessions_router.router, prefix="/api/sessions")
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[current_user_id] = lambda: "u1"
    return TestClient(app)


async def _make_session(session_factory, **overrides) -> str:
    async with session_factory() as db:
        session = DebateSession(user_id="u1", topic="AI Safety", **overrides)
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return session.id


async def test_start_session_persists_description_and_returns_has_source_false(api_client):
    resp = api_client.post(
        "/api/sessions/start",
        json={
            "topic": "AI Safety",
            "description": "Focus on EU AI Act",
            "difficulty": "targeted",
            "user_position": "against",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["description"] == "Focus on EU AI Act"
    assert body["has_source"] is False
    assert body["source_status"] == "none"


async def test_upload_source_rejects_non_pdf(api_client, session_factory):
    session_id = await _make_session(session_factory)

    resp = api_client.post(
        f"/api/sessions/{session_id}/source",
        files={"file": ("notes.txt", b"plain text", "text/plain")},
    )

    assert resp.status_code == 400


async def test_upload_source_rejects_oversized_file(api_client, session_factory, monkeypatch):
    session_id = await _make_session(session_factory)
    monkeypatch.setattr(sessions_router, "MAX_SOURCE_BYTES", 10)

    resp = api_client.post(
        f"/api/sessions/{session_id}/source",
        files={"file": ("evidence.pdf", b"x" * 100, "application/pdf")},
    )

    assert resp.status_code == 413


async def test_upload_source_enqueues_task_sets_pending_and_returns_202(
    api_client, session_factory, monkeypatch
):
    session_id = await _make_session(session_factory)
    object_key = f"sources/{session_id}/evidence.pdf"

    upload_mock = MagicMock(return_value=object_key)
    delay_mock = MagicMock()
    monkeypatch.setattr(storage_svc, "upload_source", upload_mock)
    monkeypatch.setattr(sessions_router.index_source_task, "delay", delay_mock)

    resp = api_client.post(
        f"/api/sessions/{session_id}/source",
        files={"file": ("evidence.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )

    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "pending"
    assert body["source_filename"] == "evidence.pdf"

    delay_mock.assert_called_once_with(session_id, object_key)

    async with session_factory() as db:
        result = await db.execute(select(DebateSession).where(DebateSession.id == session_id))
        session = result.scalar_one()
        assert session.source_status == "pending"
        assert session.source_filename == "evidence.pdf"
        assert session.source_object_key == object_key


async def test_get_source_status_returns_current_status(api_client, session_factory):
    session_id = await _make_session(
        session_factory,
        source_status="indexed",
        source_object_key="sources/x/e.pdf",
        source_filename="e.pdf",
    )

    resp = api_client.get(f"/api/sessions/{session_id}/source-status")

    assert resp.status_code == 200
    assert resp.json() == {"source_status": "indexed"}


async def test_get_source_status_defaults_to_none_for_new_session(api_client, session_factory):
    session_id = await _make_session(session_factory)

    resp = api_client.get(f"/api/sessions/{session_id}/source-status")

    assert resp.status_code == 200
    assert resp.json() == {"source_status": "none"}


async def test_get_source_file_returns_presigned_url(api_client, session_factory, monkeypatch):
    session_id = await _make_session(
        session_factory, source_object_key="sources/x/e.pdf", source_filename="e.pdf"
    )
    monkeypatch.setattr(
        storage_svc, "get_source_url", MagicMock(return_value="https://minio.local/presigned")
    )

    resp = api_client.get(f"/api/sessions/{session_id}/source-file")

    assert resp.status_code == 200
    assert resp.json() == {"url": "https://minio.local/presigned"}


async def test_get_source_file_404s_when_no_source(api_client, session_factory):
    session_id = await _make_session(session_factory)

    resp = api_client.get(f"/api/sessions/{session_id}/source-file")

    assert resp.status_code == 404
```

- [ ] **Step 7: Run the tests**

Run: `cd debatemind-backend && uv run pytest tests/test_sessions_router.py -v`
Expected: all 7 tests PASS.

Run the full suite: `cd debatemind-backend && uv run pytest -x -q`
Expected: all tests passing.

Run ruff: `cd debatemind-backend && uv run ruff check debatemind/routers/sessions.py`
Expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add debatemind-backend/debatemind/routers/sessions.py debatemind-backend/debatemind/schemas/session.py debatemind-backend/tests/test_sessions_router.py
git commit -m "feat: async upload endpoint (202), GET /source-status, has_source via source_status"
```

---

### Task 5: Fix cognee_svc — loud logging + asyncio timeouts + OpenRouter timeout

**Files:**
- Modify: `debatemind-backend/debatemind/services/cognee_svc.py`
- Modify: `debatemind-backend/debatemind/agents/client.py`
- Modify: `debatemind-backend/tests/test_cognee_svc.py`

**Interfaces:**
- `recall_source_context` still returns `list[dict]` (graceful degradation preserved), but now logs `logger.exception(...)` instead of silently swallowing — the caller and test both keep the same external contract
- `index_source_document` now wraps `cognee.add` with `asyncio.wait_for(..., timeout=60.0)` and `cognee.cognify` with `asyncio.wait_for(..., timeout=300.0)` — callers see `asyncio.TimeoutError` on timeout
- `recall_source_context` search call wrapped with `asyncio.wait_for(..., timeout=10.0)`
- OpenRouter client now has `timeout=httpx.Timeout(30.0, connect=5.0)`

- [ ] **Step 1: Write the failing tests for the timeout behavior**

Add to `debatemind-backend/tests/test_cognee_svc.py`:

```python
async def test_index_source_document_raises_on_timeout(monkeypatch):
    import asyncio

    async def _slow_add(*args, **kwargs):
        await asyncio.sleep(999)

    monkeypatch.setattr(cognee_svc.cognee, "add", _slow_add)
    monkeypatch.setattr(cognee_svc, "ADD_TIMEOUT", 0.01)

    with pytest.raises(asyncio.TimeoutError):
        await cognee_svc.index_source_document("s1", "/tmp/e.pdf")


async def test_recall_source_context_logs_error_and_returns_empty_on_failure(monkeypatch, caplog):
    import logging

    async def _raise(*args, **kwargs):
        raise RuntimeError("cognee misconfigured")

    monkeypatch.setattr(cognee_svc.cognee, "search", _raise)

    with caplog.at_level(logging.ERROR, logger="debatemind.services.cognee_svc"):
        results = await cognee_svc.recall_source_context("s1", "anything")

    assert results == []
    assert any("recall_source_context" in r.message.lower() or "cognee" in r.message.lower()
               for r in caplog.records)
```

Also add `import pytest` at the top of the test file if not already there.

Run: `cd debatemind-backend && uv run pytest tests/test_cognee_svc.py::test_index_source_document_raises_on_timeout tests/test_cognee_svc.py::test_recall_source_context_logs_error_and_returns_empty_on_failure -v`
Expected: FAIL (`AttributeError: module 'debatemind.services.cognee_svc' has no attribute 'ADD_TIMEOUT'`)

- [ ] **Step 2: Rewrite cognee_svc.py**

Replace the entire content of `debatemind-backend/debatemind/services/cognee_svc.py`:

```python
import asyncio
import logging

import cognee
from cognee.api.v1.search.search import SearchType

logger = logging.getLogger(__name__)

# Timeout constants — module-level so tests can monkeypatch them
ADD_TIMEOUT = 60.0
COGNIFY_TIMEOUT = 300.0
SEARCH_TIMEOUT = 10.0


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
    await asyncio.wait_for(cognee.add(text, dataset_name=dataset), timeout=ADD_TIMEOUT)
    await asyncio.wait_for(cognee.cognify(datasets=dataset), timeout=COGNIFY_TIMEOUT)


async def recall_weaknesses(user_id: str) -> list[dict]:
    results = await asyncio.wait_for(
        cognee.search(
            query_text=f"top weakness patterns and fallacies for user {user_id}",
            query_type=SearchType.GRAPH_COMPLETION,
            datasets=[_dataset(user_id)],
            top_k=10,
        ),
        timeout=SEARCH_TIMEOUT,
    )
    return [{"text": r if isinstance(r, str) else getattr(r, "text", str(r))} for r in results]


async def improve_fingerprint(user_id: str, session_id: str) -> None:
    await asyncio.wait_for(
        cognee.cognify(datasets=_dataset(user_id)), timeout=COGNIFY_TIMEOUT
    )


async def forget_pattern(user_id: str, pattern_type: str) -> None:
    dataset = _dataset(user_id)
    text = (
        f"User: {user_id}\nPattern: {pattern_type}\n"
        "Status: MASTERED\nAction: prune from opponent strategy"
    )
    await asyncio.wait_for(cognee.add(text, dataset_name=dataset), timeout=ADD_TIMEOUT)
    await asyncio.wait_for(cognee.cognify(datasets=dataset), timeout=COGNIFY_TIMEOUT)


def _source_dataset(session_id: str) -> str:
    return f"session_{session_id}_source"


async def index_source_document(session_id: str, file_path: str) -> None:
    dataset = _source_dataset(session_id)
    await asyncio.wait_for(
        cognee.add(file_path, dataset_name=dataset), timeout=ADD_TIMEOUT
    )
    await asyncio.wait_for(
        cognee.cognify(datasets=dataset), timeout=COGNIFY_TIMEOUT
    )


async def recall_source_context(session_id: str, query_text: str) -> list[dict]:
    try:
        results = await asyncio.wait_for(
            cognee.search(
                query_text=query_text,
                query_type=SearchType.CHUNKS,
                datasets=[_source_dataset(session_id)],
                top_k=5,
            ),
            timeout=SEARCH_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.error(
            "recall_source_context timed out after %.1fs for session %s",
            SEARCH_TIMEOUT,
            session_id,
        )
        return []
    except Exception:
        logger.exception(
            "recall_source_context failed for session %s query=%r", session_id, query_text
        )
        return []
    return [{"text": r if isinstance(r, str) else getattr(r, "text", str(r))} for r in results]
```

- [ ] **Step 3: Update the existing test for index_source_document**

The existing test `test_index_source_document_adds_then_cognifies_the_session_dataset` uses:
```python
add_mock.assert_awaited_once_with("/tmp/evidence.pdf", dataset_name="session_s1_source")
```
With `asyncio.wait_for` wrapping, `cognee.add` is still called with the same arguments. The `assert_awaited_once_with` assertion works on the mock itself, not on `wait_for`. The test should still pass as-is.

Run: `cd debatemind-backend && uv run pytest tests/test_cognee_svc.py -v`
Expected: all tests PASS including the 2 new ones.

- [ ] **Step 4: Add httpx.Timeout to the OpenRouter client**

Replace the content of `debatemind-backend/debatemind/agents/client.py`:

```python
import httpx
from openai import AsyncOpenAI

from debatemind.config import settings

# 30 s total timeout, 5 s connect timeout — prevents hanging workers on LLM slowdowns
openrouter: AsyncOpenAI = AsyncOpenAI(
    api_key=settings.openrouter_api_key,
    base_url=settings.openrouter_base_url,
    timeout=httpx.Timeout(30.0, connect=5.0),
)
```

- [ ] **Step 5: Run the full suite and ruff**

Run: `cd debatemind-backend && uv run pytest -x -q`
Expected: all tests PASS.

Run: `cd debatemind-backend && uv run ruff check debatemind/services/cognee_svc.py debatemind/agents/client.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add debatemind-backend/debatemind/services/cognee_svc.py debatemind-backend/debatemind/agents/client.py debatemind-backend/tests/test_cognee_svc.py
git commit -m "fix: loud error logging + asyncio timeouts in cognee_svc; httpx.Timeout on OpenRouter client"
```

---

### Task 6: Fix weakness cache + structured JSON logging

**Files:**
- Modify: `debatemind-backend/debatemind/agents/opponent.py`
- Create: `debatemind-backend/debatemind/middleware.py`
- Modify: `debatemind-backend/debatemind/main.py`
- Modify: `debatemind-backend/tests/test_opponent.py` (add 1 cache test)

**Interfaces:**
- `_weakness_cache` changes type from `dict[str, list]` to `cachetools.TTLCache[str, list]` — same access pattern, no callers need to change
- `RequestIDMiddleware` adds `X-Request-ID` header to every response and binds `request_id` to structlog context
- `setup_logging()` is called once in `main.py` before the app is created

- [ ] **Step 1: Write the failing cache test**

In `debatemind-backend/tests/test_opponent.py`, at the end of the file, add:

```python
def test_weakness_cache_has_bounded_size():
    from debatemind.agents.opponent import _weakness_cache
    # TTLCache has a maxsize attribute; plain dict does not
    assert hasattr(_weakness_cache, "maxsize")
    assert _weakness_cache.maxsize == 1024
```

Run: `cd debatemind-backend && uv run pytest tests/test_opponent.py::test_weakness_cache_has_bounded_size -v`
Expected: FAIL with `AttributeError: 'dict' object has no attribute 'maxsize'`

- [ ] **Step 2: Replace _weakness_cache with TTLCache in opponent.py**

In `debatemind-backend/debatemind/agents/opponent.py`, replace the import and cache definition:

Old:
```python
# module-level cache so recall_weaknesses is only called once per user
# across all pipeline invocations, not re-fetched on every turn.
_weakness_cache: dict[str, list] = {}
```

New:
```python
from cachetools import TTLCache

# Bounded TTL cache: max 1024 users, entries expire after 1 hour.
_weakness_cache: TTLCache = TTLCache(maxsize=1024, ttl=3600)
```

- [ ] **Step 3: Run opponent tests**

Run: `cd debatemind-backend && uv run pytest tests/test_opponent.py -v`
Expected: all tests PASS.

- [ ] **Step 4: Create middleware.py**

Create `debatemind-backend/debatemind/middleware.py`:

```python
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        with structlog.contextvars.bound_contextvars(request_id=request_id):
            response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
```

- [ ] **Step 5: Set up structlog in main.py**

Replace the full content of `debatemind-backend/debatemind/main.py`:

```python
import logging
import logging.config

import structlog
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from debatemind.config import settings
from debatemind.database import Base, engine
from debatemind.middleware import RequestIDMiddleware
from debatemind.models import mastery, session, user  # noqa: F401
from debatemind.routers import auth, sessions, topics, users
from debatemind.services.cognee_config import configure_cognee
from debatemind.services.storage_svc import ensure_bucket


def setup_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


setup_logging()

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:  # noqa: BLE001
        logger.warning("db_not_reachable", error=str(exc))

    configure_cognee(settings)

    try:
        ensure_bucket()
    except Exception as exc:  # noqa: BLE001
        logger.warning("minio_not_reachable", error=str(exc))

    yield


app = FastAPI(title="DebateMind API", lifespan=lifespan)

app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(topics.router, prefix="/api/topics", tags=["topics"])


@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 6: Run the full suite and ruff**

Run: `cd debatemind-backend && uv run pytest -x -q`
Expected: all tests PASS.

Run: `cd debatemind-backend && uv run ruff check debatemind/`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add debatemind-backend/debatemind/agents/opponent.py debatemind-backend/debatemind/middleware.py debatemind-backend/debatemind/main.py debatemind-backend/tests/test_opponent.py
git commit -m "fix: TTLCache for weakness cache; structlog JSON logging; RequestIDMiddleware"
```

---

### Task 7: Frontend — polling instead of blocking

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/components/topic/TopicSelection.tsx`

**Interfaces:**
- New `api.getSourceStatus(sessionId: string)` — calls `GET /api/sessions/{id}/source-status`, returns `{ source_status: string }`
- `api.uploadSource` return type changes to `{ status: string; source_filename: string }` (was same shape but status is now `"pending"` instead of `"indexed"`)
- TopicSelection: after `uploadSource`, polls `getSourceStatus` every 2 s; shows "Indexing your document…" spinner with a "Start debate anyway →" button; navigates automatically on `"indexed"` or `"failed"`

- [ ] **Step 1: Add getSourceStatus to api.ts**

In `frontend/src/lib/api.ts`, add this entry to the `api` object after `uploadSource`:

```typescript
  getSourceStatus: (sessionId: string) =>
    apiFetch<{ source_status: string }>(`/api/sessions/${sessionId}/source-status`),
```

The final `api` object should look like:

```typescript
export const api = {
  register: (email: string, password: string) =>
    apiFetch<{ access_token: string; user_id: string }>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  login: (email: string, password: string) =>
    apiFetch<{ access_token: string; user_id: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  startSession: (topic: string, description: string, difficulty: string, user_position: string) =>
    apiFetch<{ session_id: string; topic: string; description: string; has_source: boolean; source_status: string }>(
      "/api/sessions/start",
      {
        method: "POST",
        body: JSON.stringify({ topic, description, difficulty, user_position }),
      }
    ),
  endSession: (sessionId: string) =>
    apiFetch<{ status: string }>(`/api/sessions/${sessionId}/end`, { method: "POST" }),
  getTopics: () => apiFetch<{ label: string; chips: string[] }[]>("/api/topics/suggest"),
  getGraph: (sessionId: string) =>
    apiFetch<{ nodes: unknown[]; edges: unknown[] }>(`/api/sessions/${sessionId}/graph`),
  getProgress: () => apiFetch<ProgressData>("/api/users/me/progress"),
  uploadSource: async (sessionId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE}/api/sessions/${sessionId}/source`, {
      method: "POST",
      headers: authHeader(),
      body: form,
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json() as Promise<{ status: string; source_filename: string }>;
  },
  getSourceStatus: (sessionId: string) =>
    apiFetch<{ source_status: string }>(`/api/sessions/${sessionId}/source-status`),
  getSourceFile: (sessionId: string) =>
    apiFetch<{ url: string }>(`/api/sessions/${sessionId}/source-file`),
};
```

- [ ] **Step 2: Rewrite TopicSelection.tsx with polling**

Replace the entire content of `frontend/src/components/topic/TopicSelection.tsx`:

```tsx
"use client";
import { useState, useEffect, useRef } from "react";
import { api } from "@/lib/api";
import { useDebate } from "@/store/debate";

const DIFFICULTIES = [
  { key: "balanced", name: "Balanced", desc: "Varied angles, 60% weakness" },
  { key: "targeted", name: "Targeted", desc: "Every move hits a known weak node" },
  { key: "ruthless", name: "Ruthless", desc: "Same weakness, every angle" },
] as const;

const POSITIONS = ["For", "Against", "Neutral", "Assign randomly"] as const;
const SURPRISES = [
  "Nuclear power is the only realistic path to decarbonisation",
  "Universal basic income will erode the dignity of work",
  "Social media should be banned for under-16s",
];

const MAX_SOURCE_BYTES = 20 * 1024 * 1024;

export default function TopicSelection() {
  const [topic, setTopic] = useState("AI regulation should be government-led");
  const [description, setDescription] = useState("");
  const [activeChip, setActiveChip] = useState("");
  const [difficulty, setDifficulty] = useState<"balanced" | "targeted" | "ruthless">("targeted");
  const [position, setPosition] = useState("against");
  const [groups, setGroups] = useState<{ label: string; chips: string[] }[]>([]);
  const [sourceFile, setSourceFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState("");
  const [indexing, setIndexing] = useState(false);
  const [pendingSessionId, setPendingSessionId] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { setSession } = useDebate();

  useEffect(() => { api.getTopics().then(setGroups).catch(() => {}); }, []);

  // Clean up poll timer on unmount
  useEffect(() => () => { if (pollRef.current) clearTimeout(pollRef.current); }, []);

  function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] ?? null;
    setFileError("");
    if (file && file.type !== "application/pdf") {
      setFileError("Only PDF files are supported.");
      setSourceFile(null);
      return;
    }
    if (file && file.size > MAX_SOURCE_BYTES) {
      setFileError("File exceeds 20MB limit.");
      setSourceFile(null);
      return;
    }
    setSourceFile(file);
  }

  function navigateToSession(sessionId: string) {
    if (pollRef.current) clearTimeout(pollRef.current);
    setIndexing(false);
    setPendingSessionId(null);
    setSession(sessionId, { topic, description, difficulty, position: position as never });
  }

  function startPolling(sessionId: string) {
    const poll = async () => {
      try {
        const { source_status } = await api.getSourceStatus(sessionId);
        if (source_status === "indexed") {
          navigateToSession(sessionId);
          return;
        }
        if (source_status === "failed") {
          setFileError("Indexing failed — opponent will start without source context.");
          navigateToSession(sessionId);
          return;
        }
        // Still pending — check again in 2 s
        pollRef.current = setTimeout(poll, 2000);
      } catch {
        // Network error — navigate anyway
        navigateToSession(sessionId);
      }
    };
    pollRef.current = setTimeout(poll, 2000);
  }

  async function start() {
    setFileError("");
    const res = await api.startSession(topic, description, difficulty, position);
    if (sourceFile) {
      setIndexing(true);
      setPendingSessionId(res.session_id);
      try {
        await api.uploadSource(res.session_id, sourceFile);
        startPolling(res.session_id);
      } catch {
        setFileError("Upload failed — starting without source grounding.");
        navigateToSession(res.session_id);
      }
    } else {
      navigateToSession(res.session_id);
    }
  }

  function startAnyway() {
    if (pendingSessionId) {
      navigateToSession(pendingSessionId);
    }
  }

  return (
    <div className="max-w-3xl mx-auto px-7 py-12">
      <h1 className="font-sans font-medium text-2xl text-ink mb-5">What do you want to argue about?</h1>
      <div className="flex items-center justify-between bg-white border border-fog/30 rounded-lg px-4 py-3 mb-6">
        <span className="font-serif text-base text-ink">{topic}</span>
        <button onClick={() => { setTopic(""); setActiveChip(""); }} className="text-fog text-lg">✕</button>
      </div>

      <textarea
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder="Add context — what's the angle, what should the opponent know?"
        className="w-full bg-white border border-fog/30 rounded-lg px-4 py-3 mb-6 font-sans text-sm text-ink resize-none"
        rows={2}
      />

      {groups.map((g) => (
        <div key={g.label} className="flex gap-4 mb-3">
          <span className="w-24 flex-none font-sans text-[11px] font-semibold text-fog uppercase tracking-wide pt-1.5">{g.label}</span>
          <div className="flex flex-wrap gap-2">
            {g.chips.map((c) => (
              <button key={c} onClick={() => { setTopic(c); setActiveChip(c); }}
                className={`font-sans text-xs px-3 py-1 rounded-full border transition-all ${
                  activeChip === c ? "bg-scarlet text-white border-scarlet" : "bg-white text-ink border-fog/40"
                }`}>
                {c}
              </button>
            ))}
          </div>
        </div>
      ))}

      <button onClick={() => { const r = SURPRISES[Math.floor(Math.random() * SURPRISES.length)]; setTopic(r); setActiveChip(""); }}
        className="ml-28 font-sans text-xs text-fog border border-dashed border-fog/40 rounded-full px-3 py-1 mb-7">
        🎲 Surprise me
      </button>

      <div className="h-px bg-fog/20 my-7" />
      <p className="font-sans text-[11px] font-semibold text-fog uppercase tracking-wide mb-3">SOURCE MATERIAL (OPTIONAL)</p>
      <div className="flex items-center gap-3 mb-2">
        <label className="font-sans text-xs px-3 py-1.5 rounded-full border border-fog/40 bg-white text-ink cursor-pointer">
          Upload PDF
          <input type="file" accept="application/pdf" onChange={onFileChange} className="hidden" />
        </label>
        {sourceFile && (
          <span className="font-sans text-xs text-ink flex items-center gap-2">
            {sourceFile.name}
            <button onClick={() => setSourceFile(null)} className="text-fog">✕</button>
          </span>
        )}
      </div>
      {fileError && <p className="font-sans text-xs text-scarlet mb-5">{fileError}</p>}

      <div className="h-px bg-fog/20 my-7" />
      <p className="font-sans text-[11px] font-semibold text-fog uppercase tracking-wide mb-3">DIFFICULTY</p>
      <div className="flex gap-3 mb-7">
        {DIFFICULTIES.map((d) => (
          <div key={d.key} onClick={() => setDifficulty(d.key)}
            className={`flex-1 rounded-lg p-3 cursor-pointer border transition-all ${
              difficulty === d.key ? "border-scarlet bg-scarlet/5" : "border-fog/30 bg-white"
            }`}>
            <p className={`font-sans text-sm font-medium ${difficulty === d.key ? "text-scarlet" : "text-ink"}`}>{d.name}</p>
            <p className="font-sans text-[11px] text-fog mt-1">{d.desc}</p>
          </div>
        ))}
      </div>

      <div className="h-px bg-fog/20 my-7" />
      <p className="font-sans text-[11px] font-semibond text-fog uppercase tracking-wide mb-3">YOUR POSITION</p>
      <div className="flex mb-8">
        {POSITIONS.map((p, i) => (
          <button key={p} onClick={() => setPosition(p.toLowerCase().replace(" ", "_"))}
            className={`font-sans text-sm font-medium px-4 py-2 border border-fog/30 -ml-px transition-all
              ${i === 0 ? "rounded-l-lg" : ""} ${i === POSITIONS.length - 1 ? "rounded-r-lg" : ""}
              ${position === p.toLowerCase().replace(" ", "_") ? "bg-scarlet border-scarlet text-white z-10 relative" : "bg-white text-ink"}`}>
            {p}
          </button>
        ))}
      </div>

      <button onClick={start} disabled={indexing || !topic}
        className="w-full bg-scarlet text-white font-sans font-semibold uppercase tracking-wider text-sm py-4 rounded-lg disabled:opacity-60 mb-3">
        {indexing ? "Indexing your document…" : "Start session →"}
      </button>

      {indexing && (
        <button onClick={startAnyway}
          className="w-full border border-fog/40 text-fog font-sans text-sm py-3 rounded-lg">
          Start debate anyway →
        </button>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0, no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/components/topic/TopicSelection.tsx
git commit -m "feat: frontend polls /source-status instead of blocking; Start anyway button"
```

---

## Self-Review

**Spec coverage check:**

1. ✅ Redis + Celery: Tasks 1 + 3 + 4
2. ✅ `recall_source_context` loud error logging: Task 5 (logs `logger.exception(...)`, still returns `[]`)
3. ✅ Synchronous blocking eliminated: Task 4 (202 response, Celery task)
4. ✅ `_weakness_cache` memory leak: Task 6 (TTLCache maxsize=1024 ttl=3600)
5. ✅ OpenRouter timeout: Task 5 (`httpx.Timeout(30.0, connect=5.0)`)
6. ✅ Cognee timeouts: Task 5 (all SDK calls wrapped with `asyncio.wait_for`)
7. ✅ Structured JSON logging: Task 6 (structlog, RequestIDMiddleware)
8. ✅ Frontend polling: Task 7 (2 s poll, auto-navigate, "Start anyway" button)

**Placeholder scan:** No TBDs, no "implement later". All code blocks are complete.

**Type consistency check:**
- `source_status` column: `"none"` | `"pending"` | `"indexed"` | `"failed"` — used consistently in model (Task 2), router (Task 4), and frontend polling (Task 7)
- `index_source_task.delay(session_id, object_key)` — matches `index_source_task(self, session_id: str, object_key: str)` signature
- `_set_status(session_id, "indexed")` — correct string values throughout
- `SourceStatusOut(source_status=session.source_status)` — field name matches schema
- `ADD_TIMEOUT`, `COGNIFY_TIMEOUT`, `SEARCH_TIMEOUT` — module-level constants referenced in all `wait_for` calls
