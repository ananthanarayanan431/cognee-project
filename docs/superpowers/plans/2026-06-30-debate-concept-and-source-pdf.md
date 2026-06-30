# Debate Concept + Source PDF Grounding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user define a debate by topic + description, optionally upload a PDF as grounding material, and have the opponent agent cite real content from that PDF when arguing.

**Architecture:** PDF bytes are stored durably in MinIO (`debatemind-sources` bucket), then a local copy is handed to Cognee's `add()`/`cognify()` to build a per-session knowledge graph (`session_{id}_source` dataset). The opponent agent queries that dataset via `cognee.search(query_type=CHUNKS)` per turn and weaves the returned passages into its system prompt. Indexing is synchronous — the upload endpoint blocks until `cognify()` finishes, and the frontend shows a spinner for that window.

**Tech Stack:** FastAPI, SQLAlchemy (async, Postgres in prod / SQLite in tests), Cognee SDK (`cognee==0.1.40`), MinIO (`minio` Python SDK), Next.js/React frontend.

## Global Constraints

- PDF only — `content_type` must be `application/pdf`, else `400`.
- 20MB max upload size, else `413`.
- Presigned MinIO URLs expire after 7 days (MinIO's max).
- Source grounding affects the **opponent only** — judge scoring is unchanged.
- Indexing is **synchronous**: the upload endpoint awaits `cognify()` before returning; no background jobs or polling.
- A failed/missing source must never block starting or continuing a debate — `source_object_key` stays unset and the opponent just argues without source grounding.
- MinIO bucket name: `debatemind-sources`. Cognee dataset name per session: `f"session_{session_id}_source"`.
- Spec reference: `docs/superpowers/specs/2026-06-30-debate-concept-and-source-pdf-design.md`.

---

### Task 1: MinIO infra + config settings

**Files:**
- Modify: `docker-compose.yml`
- Modify: `debatemind-backend/pyproject.toml`
- Modify: `debatemind-backend/debatemind/config.py:1-27`
- Modify: `debatemind-backend/.env.example`
- Test: `debatemind-backend/tests/test_config.py`

**Interfaces:**
- Produces: `settings.minio_endpoint: str`, `settings.minio_access_key: str`, `settings.minio_secret_key: str`, `settings.minio_bucket: str`, `settings.minio_secure: bool` — consumed by Task 3 (`storage_svc.py`).

- [ ] **Step 1: Write the failing config test**

Append to `debatemind-backend/tests/test_config.py`:

```python
def test_minio_settings_have_local_defaults():
    settings = Settings(
        database_url="sqlite+aiosqlite:///./test.db",
        secret_key="test-secret-key-at-least-32-characters!",
        openrouter_api_key="test-key",
    )
    assert settings.minio_endpoint == "localhost:9000"
    assert settings.minio_access_key == "debatemind"
    assert settings.minio_secret_key == "debatemind123"
    assert settings.minio_bucket == "debatemind-sources"
    assert settings.minio_secure is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd debatemind-backend && uv run pytest tests/test_config.py::test_minio_settings_have_local_defaults -v`
Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'minio_endpoint'`

- [ ] **Step 3: Add MinIO settings to `Settings`**

In `debatemind-backend/debatemind/config.py`, add after the existing `cognee_db_password` line (line 20):

```python
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "debatemind"
    minio_secret_key: str = "debatemind123"
    minio_bucket: str = "debatemind-sources"
    minio_secure: bool = False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd debatemind-backend && uv run pytest tests/test_config.py -v`
Expected: PASS, all tests in the file green.

- [ ] **Step 5: Add the `minio` dependency**

Run: `cd debatemind-backend && uv add minio`
Expected: `pyproject.toml` and `uv.lock` updated with a `minio` entry; command exits 0.

- [ ] **Step 6: Add the MinIO service to `docker-compose.yml`**

In `docker-compose.yml`, add a new service after `cognee-db` (after line 34, before the closing of the `services:` block) and a matching volume entry:

```yaml
  minio:
    image: minio/minio:latest
    restart: unless-stopped
    environment:
      MINIO_ROOT_USER: debatemind
      MINIO_ROOT_PASSWORD: debatemind123
    command: server /data --console-address ":9001"
    volumes:
      - minio_data:/data
    ports:
      - "9000:9000"
      - "9001:9001"
    healthcheck:
      test: ["CMD", "mc", "ready", "local"]
      interval: 5s
      timeout: 5s
      retries: 10
```

Update the top-level `volumes:` block (originally lines 36-38) to:

```yaml
volumes:
  pgdata:
  cognee_pgdata:
  minio_data:
```

- [ ] **Step 7: Document the MinIO env vars in `.env.example`**

Append to `debatemind-backend/.env.example`:

```
# Only relevant for local dev — defaults already match the minio service in
# docker-compose.yml, override only if you changed that service.
# MINIO_ENDPOINT=localhost:9000
# MINIO_ACCESS_KEY=debatemind
# MINIO_SECRET_KEY=debatemind123
# MINIO_BUCKET=debatemind-sources
# MINIO_SECURE=false
```

- [ ] **Step 8: Bring up MinIO and verify it's reachable**

Run: `docker compose up -d minio` then `docker compose ps minio`
Expected: status `Up` / `healthy` within ~10s. Console reachable at `http://localhost:9001` (login `debatemind` / `debatemind123`).

- [ ] **Step 9: Commit**

```bash
git add docker-compose.yml debatemind-backend/pyproject.toml debatemind-backend/uv.lock debatemind-backend/debatemind/config.py debatemind-backend/.env.example debatemind-backend/tests/test_config.py
git commit -m "feat: add MinIO infra and config settings for source PDF storage"
```

---

### Task 2: Data model — session description and source fields

**Files:**
- Modify: `debatemind-backend/debatemind/models/session.py:10-21`
- Modify: `debatemind-backend/debatemind/schemas/session.py`
- Test: `debatemind-backend/tests/test_session_model.py` (new)

**Interfaces:**
- Produces: `DebateSession.description: str | None`, `DebateSession.source_filename: str | None`, `DebateSession.source_object_key: str | None`. `SessionStartIn.description: str`. `SessionOut.description: str`, `SessionOut.has_source: bool`. New schemas `SourceUploadOut`, `SourceUrlOut`.
- Consumes (test only): the `Base`/`async_sessionmaker`/in-memory-SQLite fixture pattern already used in `tests/test_progress_svc.py:14-22`.

- [ ] **Step 1: Write the failing model test**

Create `debatemind-backend/tests/test_session_model.py`:

```python
"""
Verifies the new description/source columns on DebateSession round-trip
through a real (in-memory SQLite) async session — same fixture pattern as
test_progress_svc.py.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from debatemind.database import Base
from debatemind.models.session import DebateSession


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def test_description_and_source_fields_default_to_none(db_session):
    session = DebateSession(user_id="u1", topic="AI Safety")
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)

    assert session.description is None
    assert session.source_filename is None
    assert session.source_object_key is None


async def test_description_and_source_fields_persist(db_session):
    session = DebateSession(
        user_id="u1",
        topic="AI Safety",
        description="Focus on EU AI Act enforcement",
        source_filename="report.pdf",
        source_object_key="sources/s1/report.pdf",
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)

    result = await db_session.execute(select(DebateSession).where(DebateSession.id == session.id))
    fetched = result.scalar_one()
    assert fetched.description == "Focus on EU AI Act enforcement"
    assert fetched.source_filename == "report.pdf"
    assert fetched.source_object_key == "sources/s1/report.pdf"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd debatemind-backend && uv run pytest tests/test_session_model.py -v`
Expected: FAIL — `TypeError: 'description' is an invalid keyword argument for DebateSession`

- [ ] **Step 3: Add the columns to `DebateSession`**

In `debatemind-backend/debatemind/models/session.py`, the class currently reads (lines 10-21):

```python
class DebateSession(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    topic: Mapped[str] = mapped_column(String)
    difficulty: Mapped[str] = mapped_column(String, default="targeted")
    user_position: Mapped[str] = mapped_column(String, default="against")
    status: Mapped[str] = mapped_column(String, default="active")
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)
    started_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=True)
```

Replace with:

```python
class DebateSession(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    topic: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    difficulty: Mapped[str] = mapped_column(String, default="targeted")
    user_position: Mapped[str] = mapped_column(String, default="against")
    status: Mapped[str] = mapped_column(String, default="active")
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)
    source_filename: Mapped[str] = mapped_column(String, nullable=True)
    source_object_key: Mapped[str] = mapped_column(String, nullable=True)
    started_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=True)
```

(`Text` is already imported on line 3 of this file.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd debatemind-backend && uv run pytest tests/test_session_model.py -v`
Expected: PASS

- [ ] **Step 5: Update the request/response schemas**

Replace the full contents of `debatemind-backend/debatemind/schemas/session.py` with:

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


class SourceUploadOut(BaseModel):
    status: str
    source_filename: str


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

This changes `SessionOut`'s shape (adds required `description`, optional `has_source`) — `routers/sessions.py` is updated to match in Task 7; until then `uv run pytest` for this file alone is unaffected since no test imports `SessionOut` directly yet.

- [ ] **Step 6: Note for existing local dev databases**

`Base.metadata.create_all` (run at FastAPI startup in `main.py`) only creates missing tables — it will **not** add columns to an already-existing `sessions` table. Anyone with a pre-existing local `debatemind` Postgres DB needs to run, once:

```sql
ALTER TABLE sessions ADD COLUMN description TEXT;
ALTER TABLE sessions ADD COLUMN source_filename VARCHAR;
ALTER TABLE sessions ADD COLUMN source_object_key VARCHAR;
```

(No action needed for fresh databases — `create_all` picks up the new columns automatically.)

- [ ] **Step 7: Commit**

```bash
git add debatemind-backend/debatemind/models/session.py debatemind-backend/debatemind/schemas/session.py debatemind-backend/tests/test_session_model.py
git commit -m "feat: add description and source fields to DebateSession"
```

---

### Task 3: MinIO storage service

**Files:**
- Create: `debatemind-backend/debatemind/services/storage_svc.py`
- Test: `debatemind-backend/tests/test_storage_svc.py` (new)

**Interfaces:**
- Consumes: `settings.minio_endpoint/minio_access_key/minio_secret_key/minio_bucket/minio_secure` (Task 1).
- Produces: `ensure_bucket() -> None`, `upload_source(session_id: str, filename: str, data: bytes) -> str` (returns object key), `get_source_url(object_key: str) -> str`, `download_to_tempfile(object_key: str) -> Path` — all consumed by Task 7 (router) and Task 8 (`main.py` startup).

- [ ] **Step 1: Write the failing tests**

Create `debatemind-backend/tests/test_storage_svc.py`:

```python
"""
Unit tests for storage_svc — verifies the MinIO client is called with the
right bucket/object-key/content-type. The MinIO client itself is mocked via
_get_client(); no real MinIO I/O happens here.
"""

from datetime import timedelta
from unittest.mock import MagicMock

from debatemind.services import storage_svc


def test_upload_source_puts_object_under_session_scoped_key(monkeypatch):
    mock_client = MagicMock()
    monkeypatch.setattr(storage_svc, "_get_client", lambda: mock_client)

    object_key = storage_svc.upload_source("s1", "evidence.pdf", b"%PDF-1.4 fake content")

    assert object_key == "sources/s1/evidence.pdf"
    mock_client.put_object.assert_called_once()
    args, kwargs = mock_client.put_object.call_args
    assert args[0] == storage_svc.settings.minio_bucket
    assert args[1] == "sources/s1/evidence.pdf"
    assert kwargs["length"] == len(b"%PDF-1.4 fake content")
    assert kwargs["content_type"] == "application/pdf"


def test_upload_source_uses_only_the_basename_of_the_filename(monkeypatch):
    mock_client = MagicMock()
    monkeypatch.setattr(storage_svc, "_get_client", lambda: mock_client)

    object_key = storage_svc.upload_source("s1", "../../etc/evidence.pdf", b"data")

    assert object_key == "sources/s1/evidence.pdf"


def test_get_source_url_returns_a_presigned_url_with_seven_day_expiry(monkeypatch):
    mock_client = MagicMock()
    mock_client.presigned_get_object.return_value = "https://minio.local/presigned"
    monkeypatch.setattr(storage_svc, "_get_client", lambda: mock_client)

    url = storage_svc.get_source_url("sources/s1/evidence.pdf")

    assert url == "https://minio.local/presigned"
    mock_client.presigned_get_object.assert_called_once_with(
        storage_svc.settings.minio_bucket,
        "sources/s1/evidence.pdf",
        expires=timedelta(days=7),
    )


def test_download_to_tempfile_calls_fget_object_and_returns_a_pdf_path(monkeypatch):
    mock_client = MagicMock()
    monkeypatch.setattr(storage_svc, "_get_client", lambda: mock_client)

    result = storage_svc.download_to_tempfile("sources/s1/evidence.pdf")

    mock_client.fget_object.assert_called_once()
    call_args = mock_client.fget_object.call_args.args
    assert call_args[0] == storage_svc.settings.minio_bucket
    assert call_args[1] == "sources/s1/evidence.pdf"
    assert str(result) == call_args[2]
    assert result.suffix == ".pdf"


def test_ensure_bucket_creates_bucket_when_missing(monkeypatch):
    mock_client = MagicMock()
    mock_client.bucket_exists.return_value = False
    monkeypatch.setattr(storage_svc, "_get_client", lambda: mock_client)

    storage_svc.ensure_bucket()

    mock_client.make_bucket.assert_called_once_with(storage_svc.settings.minio_bucket)


def test_ensure_bucket_skips_creation_when_bucket_exists(monkeypatch):
    mock_client = MagicMock()
    mock_client.bucket_exists.return_value = True
    monkeypatch.setattr(storage_svc, "_get_client", lambda: mock_client)

    storage_svc.ensure_bucket()

    mock_client.make_bucket.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd debatemind-backend && uv run pytest tests/test_storage_svc.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'debatemind.services.storage_svc'`

- [ ] **Step 3: Implement `storage_svc.py`**

Create `debatemind-backend/debatemind/services/storage_svc.py`:

```python
import os
import tempfile
from datetime import timedelta
from io import BytesIO
from pathlib import Path

from minio import Minio

from debatemind.config import settings

_client: Minio | None = None


def _get_client() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
    return _client


def ensure_bucket() -> None:
    client = _get_client()
    if not client.bucket_exists(settings.minio_bucket):
        client.make_bucket(settings.minio_bucket)


def upload_source(session_id: str, filename: str, data: bytes) -> str:
    safe_filename = Path(filename).name
    object_key = f"sources/{session_id}/{safe_filename}"
    client = _get_client()
    client.put_object(
        settings.minio_bucket,
        object_key,
        BytesIO(data),
        length=len(data),
        content_type="application/pdf",
    )
    return object_key


def get_source_url(object_key: str) -> str:
    client = _get_client()
    return client.presigned_get_object(
        settings.minio_bucket, object_key, expires=timedelta(days=7)
    )


def download_to_tempfile(object_key: str) -> Path:
    client = _get_client()
    suffix = Path(object_key).suffix
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    client.fget_object(settings.minio_bucket, object_key, tmp_path)
    return Path(tmp_path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd debatemind-backend && uv run pytest tests/test_storage_svc.py -v`
Expected: PASS, all 6 tests green.

- [ ] **Step 5: Commit**

```bash
git add debatemind-backend/debatemind/services/storage_svc.py debatemind-backend/tests/test_storage_svc.py
git commit -m "feat: add MinIO storage service for source PDFs"
```

---

### Task 4: Cognee per-session source ingestion and search

**Files:**
- Modify: `debatemind-backend/debatemind/services/cognee_svc.py`
- Modify: `debatemind-backend/tests/test_cognee_svc.py`

**Interfaces:**
- Produces: `index_source_document(session_id: str, file_path: str) -> None`, `recall_source_context(session_id: str, query_text: str) -> list[dict]` (shape `[{"text": str}, ...]`, same as existing `recall_weaknesses`) — consumed by Task 6 (`opponent.py`) and Task 7 (router).

- [ ] **Step 1: Write the failing tests**

Append to `debatemind-backend/tests/test_cognee_svc.py`:

```python
async def test_index_source_document_adds_then_cognifies_the_session_dataset(monkeypatch):
    add_mock = AsyncMock()
    cognify_mock = AsyncMock()
    monkeypatch.setattr(cognee_svc.cognee, "add", add_mock)
    monkeypatch.setattr(cognee_svc.cognee, "cognify", cognify_mock)

    await cognee_svc.index_source_document("s1", "/tmp/evidence.pdf")

    add_mock.assert_awaited_once_with("/tmp/evidence.pdf", dataset_name="session_s1_source")
    cognify_mock.assert_awaited_once_with(datasets="session_s1_source")


async def test_recall_source_context_searches_chunks_for_the_session_dataset(monkeypatch):
    search_mock = AsyncMock(return_value=["Quote from the PDF", "Another quote"])
    monkeypatch.setattr(cognee_svc.cognee, "search", search_mock)

    results = await cognee_svc.recall_source_context("s1", "is nuclear power safe?")

    search_mock.assert_awaited_once()
    kwargs = search_mock.call_args.kwargs
    assert kwargs["query_type"] == cognee_svc.SearchType.CHUNKS
    assert kwargs["datasets"] == ["session_s1_source"]
    assert kwargs["top_k"] == 5
    assert kwargs["query_text"] == "is nuclear power safe?"
    assert results == [{"text": "Quote from the PDF"}, {"text": "Another quote"}]


async def test_recall_source_context_returns_empty_list_when_dataset_missing(monkeypatch):
    async def _raise(*args, **kwargs):
        raise Exception("dataset not found")

    monkeypatch.setattr(cognee_svc.cognee, "search", _raise)

    results = await cognee_svc.recall_source_context("s1", "anything")

    assert results == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd debatemind-backend && uv run pytest tests/test_cognee_svc.py -v`
Expected: FAIL with `AttributeError: module 'debatemind.services.cognee_svc' has no attribute 'index_source_document'`

- [ ] **Step 3: Implement the new functions**

Append to `debatemind-backend/debatemind/services/cognee_svc.py` (after `forget_pattern`, end of file):

```python


def _source_dataset(session_id: str) -> str:
    return f"session_{session_id}_source"


async def index_source_document(session_id: str, file_path: str) -> None:
    dataset = _source_dataset(session_id)
    await cognee.add(file_path, dataset_name=dataset)
    await cognee.cognify(datasets=dataset)


async def recall_source_context(session_id: str, query_text: str) -> list[dict]:
    try:
        results = await cognee.search(
            query_text=query_text,
            query_type=SearchType.CHUNKS,
            datasets=[_source_dataset(session_id)],
            top_k=5,
        )
    except Exception:
        return []
    return [{"text": r if isinstance(r, str) else getattr(r, "text", str(r))} for r in results]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd debatemind-backend && uv run pytest tests/test_cognee_svc.py -v`
Expected: PASS, all tests in the file green (existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add debatemind-backend/debatemind/services/cognee_svc.py debatemind-backend/tests/test_cognee_svc.py
git commit -m "feat: add per-session Cognee source document indexing and search"
```

---

### Task 5: Prompt updates — description and source context

**Files:**
- Modify: `debatemind-backend/debatemind/agents/prompts/extractor.py`
- Modify: `debatemind-backend/debatemind/agents/prompts/opponent.py`
- Modify: `debatemind-backend/tests/test_prompts.py`

**Interfaces:**
- Produces: `extractor_prompt(topic: str, argument: str, description: str = "") -> str`, `opponent_system_prompt(weakness_text: str, difficulty: str, source_text: str = "") -> str`, `opponent_user_message(topic: str, user_argument: str, description: str = "") -> str` — consumed by Task 6 (`extractor.py`, `opponent.py`).

- [ ] **Step 1: Write the failing tests**

Append to the `TestExtractorPrompt` class in `debatemind-backend/tests/test_prompts.py`:

```python
    def test_includes_description_when_present(self):
        p = extractor_prompt("Climate change", "We must cut emissions now", description="Focus on EU policy")
        assert "Focus on EU policy" in p

    def test_omits_context_line_when_description_absent(self):
        p = extractor_prompt("topic", "arg")
        assert "Context:" not in p
```

Append to the `TestOpponentPrompts` class in the same file:

```python
    def test_system_prompt_includes_source_text_when_present(self):
        p = opponent_system_prompt("weakness A", "targeted", source_text="The report states X causes Y.")
        assert "The report states X causes Y." in p
        assert "Source material" in p

    def test_system_prompt_omits_source_block_when_absent(self):
        p = opponent_system_prompt("weakness A", "targeted")
        assert "Source material" not in p

    def test_user_message_includes_description_when_present(self):
        m = opponent_user_message(
            "Tax policy", "higher taxes reduce inequality", description="Focus on US federal brackets"
        )
        assert "Focus on US federal brackets" in m

    def test_user_message_omits_context_line_when_description_absent(self):
        m = opponent_user_message("Tax policy", "higher taxes reduce inequality")
        assert "Context:" not in m
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd debatemind-backend && uv run pytest tests/test_prompts.py -v`
Expected: FAIL — `TypeError: extractor_prompt() got an unexpected keyword argument 'description'` (and similarly for the opponent prompt tests).

- [ ] **Step 3: Update `extractor_prompt`**

Replace `debatemind-backend/debatemind/agents/prompts/extractor.py` with:

```python
from debatemind.agents.constants import PATTERN_TYPES


def extractor_prompt(topic: str, argument: str, description: str = "") -> str:
    context_line = f"Context: {description}\n" if description else ""
    return f"""Analyze this debate argument and return JSON only.

Topic: {topic}
{context_line}Argument: {argument}

Return exactly:
{{
  "pattern_type": "<one of: {", ".join(PATTERN_TYPES)}>",
  "fallacy": "<fallacy name or null>",
  "evidence_quality": "<Strong|Moderate|Weak|Absent>"
}}"""
```

- [ ] **Step 4: Update the opponent prompts**

Replace `debatemind-backend/debatemind/agents/prompts/opponent.py` with:

```python
_DIFFICULTY_INSTRUCTIONS = {
    "balanced": "Explore multiple angles; target a known weakness ~60% of the time.",
    "targeted": "Every response MUST target one of the user's listed weakness patterns.",
    "ruthless": "Hammer the same weakness from different angles until they find a true counter.",
}


def opponent_system_prompt(weakness_text: str, difficulty: str, source_text: str = "") -> str:
    instruction = _DIFFICULTY_INSTRUCTIONS.get(difficulty, _DIFFICULTY_INSTRUCTIONS["targeted"])
    prompt = f"""You are a world-class debate opponent.

User's cognitive fingerprint (known weaknesses):
{weakness_text}

Difficulty: {difficulty}
Instruction: {instruction}

Rules:
- Respond with a sharp, substantive counter-argument. No softening.
- Never concede unless the user's argument is genuinely irrefutable.
- Do NOT repeat an argument pattern you already used this session.
- Keep response under 120 words."""
    if source_text:
        prompt += (
            f"\n\nSource material the user provided "
            f"(cite specifics from this when relevant):\n{source_text}"
        )
    return prompt


def opponent_user_message(topic: str, user_argument: str, description: str = "") -> str:
    context_line = f"\n\nContext: {description}" if description else ""
    return f"Topic: {topic}{context_line}\n\nUser argues: {user_argument}"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd debatemind-backend && uv run pytest tests/test_prompts.py -v`
Expected: PASS, all tests in the file green (existing + 4 new).

- [ ] **Step 6: Commit**

```bash
git add debatemind-backend/debatemind/agents/prompts/extractor.py debatemind-backend/debatemind/agents/prompts/opponent.py debatemind-backend/tests/test_prompts.py
git commit -m "feat: thread description and source context into extractor/opponent prompts"
```

---

### Task 6: Wire state, extractor, and opponent agents to source context

**Files:**
- Modify: `debatemind-backend/debatemind/agents/state.py`
- Modify: `debatemind-backend/debatemind/agents/extractor.py`
- Modify: `debatemind-backend/debatemind/agents/opponent.py`
- Test: `debatemind-backend/tests/test_opponent.py` (new)

**Interfaces:**
- Consumes: `recall_source_context` (Task 4), `opponent_system_prompt`/`opponent_user_message`/`extractor_prompt` (Task 5).
- Produces: `DebateState` gains `description: Optional[str]`, `has_source: bool`, `source_context: list[dict]` — consumed by Task 7 (`routers/sessions.py` builds `initial_state`).

- [ ] **Step 1: Add fields to `DebateState`**

In `debatemind-backend/debatemind/agents/state.py`, the class currently reads:

```python
class DebateState(TypedDict):
    user_id: str
    session_id: str
    topic: str
    difficulty: str
    user_position: str
    user_message: str
    turn_number: int
    consecutive_wins: int
    extracted_pattern: Optional[str]
    extracted_fallacy: Optional[str]
    evidence_quality: Optional[str]
    weakness_context: list[dict]
    opponent_response: Optional[str]
    judge_logic: Optional[float]
    judge_evidence: Optional[float]
    judge_rhetoric: Optional[float]
    judge_fallacy: Optional[str]
    outcome: Optional[str]
    mastery_events: list[str]
    _prev_pattern: Optional[str]  # mastery.py tracks pattern continuity across turns
```

Replace with:

```python
class DebateState(TypedDict):
    user_id: str
    session_id: str
    topic: str
    description: Optional[str]
    difficulty: str
    user_position: str
    user_message: str
    turn_number: int
    consecutive_wins: int
    has_source: bool
    source_context: list[dict]
    extracted_pattern: Optional[str]
    extracted_fallacy: Optional[str]
    evidence_quality: Optional[str]
    weakness_context: list[dict]
    opponent_response: Optional[str]
    judge_logic: Optional[float]
    judge_evidence: Optional[float]
    judge_rhetoric: Optional[float]
    judge_fallacy: Optional[str]
    outcome: Optional[str]
    mastery_events: list[str]
    _prev_pattern: Optional[str]  # mastery.py tracks pattern continuity across turns
```

- [ ] **Step 2: Pass `description` through the extractor**

In `debatemind-backend/debatemind/agents/extractor.py`, line 10 currently reads:

```python
    prompt = extractor_prompt(state["topic"], state["user_message"])
```

Replace with:

```python
    prompt = extractor_prompt(state["topic"], state["user_message"], state.get("description") or "")
```

- [ ] **Step 3: Write the failing opponent tests**

Create `debatemind-backend/tests/test_opponent.py`:

```python
"""
Unit tests for opponent.generate_opponent — verifies weakness and source
context wiring. The OpenRouter LLM call and both Cognee recall functions are
mocked; no real network or Cognee calls happen here.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from debatemind.agents import opponent as opponent_module


def _state(**overrides) -> dict:
    base: dict = {
        "user_id": "u1",
        "session_id": "s1",
        "topic": "AI Safety",
        "description": "",
        "difficulty": "targeted",
        "user_position": "against",
        "user_message": "test argument",
        "turn_number": 1,
        "consecutive_wins": 0,
        "has_source": False,
        "source_context": [],
        "weakness_context": [],
        "extracted_pattern": None,
        "extracted_fallacy": None,
        "evidence_quality": None,
        "opponent_response": None,
        "judge_logic": None,
        "judge_evidence": None,
        "judge_rhetoric": None,
        "judge_fallacy": None,
        "outcome": None,
        "mastery_events": [],
    }
    base.update(overrides)
    return base


def _mock_llm_response(text="A counter-argument."):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


async def test_skips_source_recall_when_session_has_no_source(monkeypatch):
    opponent_module._weakness_cache.clear()
    monkeypatch.setattr(opponent_module, "recall_weaknesses", AsyncMock(return_value=[]))
    source_mock = AsyncMock()
    monkeypatch.setattr(opponent_module, "recall_source_context", source_mock)
    monkeypatch.setattr(
        opponent_module.openrouter.chat.completions,
        "create",
        AsyncMock(return_value=_mock_llm_response()),
    )

    await opponent_module.generate_opponent(_state(has_source=False))

    source_mock.assert_not_called()


async def test_fetches_and_includes_source_context_when_session_has_source(monkeypatch):
    opponent_module._weakness_cache.clear()
    monkeypatch.setattr(opponent_module, "recall_weaknesses", AsyncMock(return_value=[]))
    source_mock = AsyncMock(return_value=[{"text": "The report says X."}])
    monkeypatch.setattr(opponent_module, "recall_source_context", source_mock)
    llm_mock = AsyncMock(return_value=_mock_llm_response())
    monkeypatch.setattr(opponent_module.openrouter.chat.completions, "create", llm_mock)

    result = await opponent_module.generate_opponent(_state(has_source=True, session_id="s9"))

    source_mock.assert_awaited_once_with("s9", "test argument")
    assert result["source_context"] == [{"text": "The report says X."}]
    system_msg = llm_mock.call_args.kwargs["messages"][0]["content"]
    assert "The report says X." in system_msg
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `cd debatemind-backend && uv run pytest tests/test_opponent.py -v`
Expected: FAIL — `AttributeError: module 'debatemind.agents.opponent' has no attribute 'recall_source_context'`

- [ ] **Step 5: Wire `generate_opponent` to fetch and use source context**

Replace the full contents of `debatemind-backend/debatemind/agents/opponent.py` with:

```python
from debatemind.agents.client import openrouter
from debatemind.agents.prompts.opponent import opponent_system_prompt, opponent_user_message
from debatemind.agents.state import DebateState
from debatemind.config import settings
from debatemind.services.cognee_svc import recall_source_context, recall_weaknesses

# module-level cache so recall_weaknesses is only called once per user
# across all pipeline invocations, not re-fetched on every turn.
_weakness_cache: dict[str, list] = {}


async def generate_opponent(state: DebateState) -> DebateState:
    user_id = state["user_id"]

    if user_id not in _weakness_cache:
        _weakness_cache[user_id] = await recall_weaknesses(user_id)

    state["weakness_context"] = _weakness_cache[user_id]

    source_context: list[dict] = []
    if state.get("has_source"):
        source_context = await recall_source_context(state["session_id"], state["user_message"])
    state["source_context"] = source_context

    weakness_text = (
        "\n".join(r.get("text", "") for r in state["weakness_context"][:5])
        or "No prior weaknesses recorded — probe broadly."
    )
    source_text = "\n".join(r.get("text", "") for r in source_context[:5])

    difficulty = state.get("difficulty", "targeted")

    msg = await openrouter.chat.completions.create(
        model=settings.main_model,
        max_tokens=300,
        messages=[
            {
                "role": "system",
                "content": opponent_system_prompt(weakness_text, difficulty, source_text),
            },
            {
                "role": "user",
                "content": opponent_user_message(
                    state["topic"], state["user_message"], state.get("description") or ""
                ),
            },
        ],
    )
    state["opponent_response"] = msg.choices[0].message.content or ""
    return state
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd debatemind-backend && uv run pytest tests/test_opponent.py -v`
Expected: PASS, both tests green.

- [ ] **Step 7: Run the full backend test suite to catch breakage from the `DebateState` change**

Run: `cd debatemind-backend && uv run pytest -v`
Expected: All tests pass. `test_mastery.py`'s `_state()` helper doesn't set `description`/`has_source`/`source_context`, but `check_mastery` never reads those keys, so this should already pass — if it doesn't, add the three missing keys to that helper's `base` dict (`"description": "", "has_source": False, "source_context": []`).

- [ ] **Step 8: Commit**

```bash
git add debatemind-backend/debatemind/agents/state.py debatemind-backend/debatemind/agents/extractor.py debatemind-backend/debatemind/agents/opponent.py debatemind-backend/tests/test_opponent.py
git commit -m "feat: ground opponent responses in per-session source context"
```

---

### Task 7: Sessions router — concept input, upload endpoint, source-file endpoint

**Files:**
- Modify: `debatemind-backend/debatemind/routers/sessions.py`
- Test: `debatemind-backend/tests/test_sessions_router.py` (new)

**Interfaces:**
- Consumes: `SessionStartIn`/`SessionOut`/`SourceUploadOut`/`SourceUrlOut` (Task 2), `DebateSession.description/source_filename/source_object_key` (Task 2), `storage_svc.upload_source/download_to_tempfile/get_source_url` (Task 3), `cognee_svc.index_source_document` (Task 4), `DebateState.description/has_source/source_context` (Task 6).
- Produces: `MAX_SOURCE_BYTES` (module constant, used by the test to simulate oversized uploads), routes `POST /{session_id}/source`, `GET /{session_id}/source-file`.

- [ ] **Step 1: Write the failing router tests**

Create `debatemind-backend/tests/test_sessions_router.py`:

```python
"""
API-level tests for the sessions router's concept/source-upload endpoints.
storage_svc (MinIO) and cognee_svc.index_source_document are mocked so no
real MinIO/Cognee I/O happens; the DB layer is a real in-memory SQLite,
same pattern as test_progress_svc.py.
"""

from unittest.mock import AsyncMock, MagicMock

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
        json={"topic": "AI Safety", "description": "Focus on EU AI Act", "difficulty": "targeted", "user_position": "against"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["description"] == "Focus on EU AI Act"
    assert body["has_source"] is False


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


async def test_upload_source_indexes_pdf_and_persists_object_key(
    api_client, session_factory, monkeypatch, tmp_path
):
    session_id = await _make_session(session_factory)
    fake_local_path = tmp_path / "evidence.pdf"
    fake_local_path.write_bytes(b"local copy")
    object_key = f"sources/{session_id}/evidence.pdf"

    upload_mock = MagicMock(return_value=object_key)
    download_mock = MagicMock(return_value=fake_local_path)
    index_mock = AsyncMock()
    monkeypatch.setattr(storage_svc, "upload_source", upload_mock)
    monkeypatch.setattr(storage_svc, "download_to_tempfile", download_mock)
    monkeypatch.setattr(sessions_router, "index_source_document", index_mock)

    resp = api_client.post(
        f"/api/sessions/{session_id}/source",
        files={"file": ("evidence.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )

    assert resp.status_code == 200
    assert resp.json() == {"status": "indexed", "source_filename": "evidence.pdf"}
    upload_mock.assert_called_once_with(session_id, "evidence.pdf", b"%PDF-1.4 fake")
    index_mock.assert_awaited_once_with(session_id, str(fake_local_path))
    assert not fake_local_path.exists()

    async with session_factory() as db:
        result = await db.execute(select(DebateSession).where(DebateSession.id == session_id))
        session = result.scalar_one()
        assert session.source_object_key == object_key
        assert session.source_filename == "evidence.pdf"


async def test_upload_source_500s_and_leaves_session_ungrounded_when_indexing_fails(
    api_client, session_factory, monkeypatch, tmp_path
):
    session_id = await _make_session(session_factory)
    fake_local_path = tmp_path / "evidence.pdf"
    fake_local_path.write_bytes(b"local copy")

    monkeypatch.setattr(storage_svc, "upload_source", MagicMock(return_value="key"))
    monkeypatch.setattr(storage_svc, "download_to_tempfile", MagicMock(return_value=fake_local_path))
    monkeypatch.setattr(
        sessions_router, "index_source_document", AsyncMock(side_effect=RuntimeError("cognee down"))
    )

    resp = api_client.post(
        f"/api/sessions/{session_id}/source",
        files={"file": ("evidence.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )

    assert resp.status_code == 500

    async with session_factory() as db:
        result = await db.execute(select(DebateSession).where(DebateSession.id == session_id))
        session = result.scalar_one()
        assert session.source_object_key is None


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

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd debatemind-backend && uv run pytest tests/test_sessions_router.py -v`
Expected: FAIL — `test_start_session_persists_description...` fails on `body["description"]` (current `SessionOut` doesn't return it); upload/source-file tests fail with `404`/`405` since those routes don't exist yet.

- [ ] **Step 3: Update imports and add `MAX_SOURCE_BYTES`**

In `debatemind-backend/debatemind/routers/sessions.py`, replace everything from the top of the file through the `_session_wins` declaration (lines 1-23) with:

```python
import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
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
    SourceUploadOut,
    SourceUrlOut,
)
from debatemind.services import storage_svc
from debatemind.services.cognee_svc import improve_fingerprint, index_source_document
from debatemind.services.graph_svc import build_graph

router = APIRouter()

# In-memory consecutive-wins counter per session (resets on server restart).
_session_wins: dict[str, int] = {}

MAX_SOURCE_BYTES = 20 * 1024 * 1024
```

- [ ] **Step 4: Update `start_session` to persist `description` and return the new fields**

Replace the `start_session` function (originally lines 26-42) with:

```python
@router.post("/start", response_model=SessionOut)
async def start_session(
    body: SessionStartIn,
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    session = DebateSession(
        user_id=user_id,
        topic=body.topic,
        description=body.description,
        difficulty=body.difficulty,
        user_position=body.user_position,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    _session_wins[session.id] = 0
    return SessionOut(
        session_id=session.id,
        topic=session.topic,
        description=session.description or "",
        difficulty=session.difficulty,
        has_source=False,
    )
```

- [ ] **Step 5: Add `description`/`has_source` to the pipeline's `initial_state`**

In `send_message`, the `initial_state = DebateState(...)` block currently reads:

```python
    initial_state = DebateState(
        user_id=user_id,
        session_id=session_id,
        topic=session.topic,
        difficulty=session.difficulty,
        user_position=session.user_position,
        user_message=body.text,
        turn_number=turn,
        consecutive_wins=_session_wins.get(session_id, 0),
        extracted_pattern=None,
        extracted_fallacy=None,
        evidence_quality=None,
        weakness_context=[],
        opponent_response=None,
        judge_logic=None,
        judge_evidence=None,
        judge_rhetoric=None,
        judge_fallacy=None,
        outcome=None,
        mastery_events=[],
    )
```

Replace with:

```python
    initial_state = DebateState(
        user_id=user_id,
        session_id=session_id,
        topic=session.topic,
        description=session.description or "",
        difficulty=session.difficulty,
        user_position=session.user_position,
        user_message=body.text,
        turn_number=turn,
        consecutive_wins=_session_wins.get(session_id, 0),
        has_source=bool(session.source_object_key),
        source_context=[],
        extracted_pattern=None,
        extracted_fallacy=None,
        evidence_quality=None,
        weakness_context=[],
        opponent_response=None,
        judge_logic=None,
        judge_evidence=None,
        judge_rhetoric=None,
        judge_fallacy=None,
        outcome=None,
        mastery_events=[],
    )
```

- [ ] **Step 6: Add the upload and source-file endpoints**

Insert the following two route handlers immediately after `start_session` (before `send_message`):

```python
@router.post("/{session_id}/source", response_model=SourceUploadOut)
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

    try:
        tmp_path = storage_svc.download_to_tempfile(object_key)
        try:
            await index_source_document(session_id, str(tmp_path))
        finally:
            tmp_path.unlink(missing_ok=True)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Indexing failed: {exc}") from exc

    await db.execute(
        update(DebateSession)
        .where(DebateSession.id == session_id)
        .values(source_filename=file.filename, source_object_key=object_key)
    )
    await db.commit()

    return SourceUploadOut(status="indexed", source_filename=file.filename)


@router.get("/{session_id}/source-file", response_model=SourceUrlOut)
async def get_source_file(
    session_id: str,
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(DebateSession).where(DebateSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session or session.user_id != user_id:
        raise HTTPException(status_code=404, detail="Session not found")
    if not session.source_object_key:
        raise HTTPException(status_code=404, detail="No source file for this session")
    return SourceUrlOut(url=storage_svc.get_source_url(session.source_object_key))
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd debatemind-backend && uv run pytest tests/test_sessions_router.py -v`
Expected: PASS, all 7 tests green.

- [ ] **Step 8: Run the full backend test suite**

Run: `cd debatemind-backend && uv run pytest -v`
Expected: All tests pass.

- [ ] **Step 9: Commit**

```bash
git add debatemind-backend/debatemind/routers/sessions.py debatemind-backend/tests/test_sessions_router.py
git commit -m "feat: add description concept and source PDF upload endpoints"
```

---

### Task 8: Initialize the MinIO bucket at startup

**Files:**
- Modify: `debatemind-backend/debatemind/main.py`

**Interfaces:**
- Consumes: `storage_svc.ensure_bucket()` (Task 3).

- [ ] **Step 1: Call `ensure_bucket()` in the lifespan**

In `debatemind-backend/debatemind/main.py`, the import block (lines 1-11) and lifespan (lines 16-26) currently read:

```python
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

Replace with:

```python
from debatemind.config import settings
from debatemind.database import Base, engine
from debatemind.models import mastery, session, user  # noqa: F401
from debatemind.routers import auth, sessions, topics, users
from debatemind.services.cognee_config import configure_cognee
from debatemind.services.storage_svc import ensure_bucket

logger = logging.getLogger("debatemind")


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:  # noqa: BLE001
        logger.warning("DB not reachable at startup: %s", exc)

    configure_cognee(settings)

    try:
        ensure_bucket()
    except Exception as exc:  # noqa: BLE001
        logger.warning("MinIO not reachable at startup: %s", exc)

    yield
```

(Matches the existing "warn, don't crash" pattern already used for the DB connection above it.)

- [ ] **Step 2: Verify the backend starts cleanly**

Run: `docker compose up -d` then `cd debatemind-backend && uv run uvicorn debatemind.main:app --port 8001` (Ctrl-C after confirming startup)
Expected: log line `Application startup complete`, no MinIO warning (since `docker compose up -d` includes the `minio` service from Task 1).

- [ ] **Step 3: Run the full backend test suite once more**

Run: `cd debatemind-backend && uv run pytest -v`
Expected: All tests pass (this task touches no test-covered logic, just startup wiring — confirms nothing regressed).

- [ ] **Step 4: Commit**

```bash
git add debatemind-backend/debatemind/main.py
git commit -m "feat: create the MinIO source bucket at app startup"
```

---

### Task 9: Frontend — concept input and PDF upload

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/components/topic/TopicSelection.tsx`

**Interfaces:**
- Consumes: `POST /api/sessions/start` (now accepts `description`), `POST /api/sessions/{id}/source` (Task 7), `GET /api/sessions/{id}/source-file` (Task 7).
- Produces: `SessionConfig.description: string`, `api.uploadSource(sessionId, file)`, `api.getSourceFile(sessionId)`.

- [ ] **Step 1: Add `description` to `SessionConfig`**

In `frontend/src/types/index.ts`, replace lines 35-39:

```typescript
export interface SessionConfig {
  topic: string;
  difficulty: "balanced" | "targeted" | "ruthless";
  position: "for" | "against" | "neutral";
}
```

with:

```typescript
export interface SessionConfig {
  topic: string;
  description: string;
  difficulty: "balanced" | "targeted" | "ruthless";
  position: "for" | "against" | "neutral";
}
```

- [ ] **Step 2: Add `description` to `startSession` and new upload/source-file calls**

In `frontend/src/lib/api.ts`, replace the `startSession` entry (lines 28-32) and add two new entries after `getGraph` (before the closing `};` on line 38):

```typescript
  startSession: (topic: string, description: string, difficulty: string, user_position: string) =>
    apiFetch<{ session_id: string; topic: string; description: string; has_source: boolean }>(
      "/api/sessions/start",
      {
        method: "POST",
        body: JSON.stringify({ topic, description, difficulty, user_position }),
      }
    ),
```

```typescript
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
  getSourceFile: (sessionId: string) =>
    apiFetch<{ url: string }>(`/api/sessions/${sessionId}/source-file`),
```

(`uploadSource` bypasses `apiFetch` deliberately — that helper always sets `Content-Type: application/json`, which would break the multipart boundary the browser needs to set itself for `FormData`.)

- [ ] **Step 3: Add the description textarea, PDF picker, and indexing flow to `TopicSelection.tsx`**

In `frontend/src/components/topic/TopicSelection.tsx`, replace the full file with:

```tsx
"use client";
import { useState, useEffect } from "react";
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
  const { setSession } = useDebate();

  useEffect(() => { api.getTopics().then(setGroups).catch(() => {}); }, []);

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

  async function start() {
    const res = await api.startSession(topic, description, difficulty, position);
    if (sourceFile) {
      setIndexing(true);
      try {
        await api.uploadSource(res.session_id, sourceFile);
      } catch {
        setFileError("Indexing failed — starting without source grounding.");
      } finally {
        setIndexing(false);
      }
    }
    setSession(res.session_id, { topic, description, difficulty, position: position as never });
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
      <p className="font-sans text-[11px] font-semibold text-fog uppercase tracking-wide mb-3">YOUR POSITION</p>
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

      <button onClick={start} disabled={indexing}
        className="w-full bg-scarlet text-white font-sans font-semibold uppercase tracking-wider text-sm py-4 rounded-lg disabled:opacity-60">
        {indexing ? "Indexing your document…" : "Start session →"}
      </button>
    </div>
  );
}
```

- [ ] **Step 4: Type-check and lint**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: No type errors, no lint errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/lib/api.ts frontend/src/components/topic/TopicSelection.tsx
git commit -m "feat: add concept description and PDF source upload to topic screen"
```

---

### Task 10: End-to-end manual verification

**Files:** none (verification only)

- [ ] **Step 1: Bring up infra and both apps**

Run: `docker compose up -d` (now includes `minio`), then `make dev` (or `make debatemind-backend` and `make frontend` in separate terminals).
Expected: backend on `:8001`, frontend on `:3000`, all three `docker compose ps` services healthy.

- [ ] **Step 2: Start a debate with no PDF (regression check)**

In the browser: register/login, enter a topic + description, leave the PDF picker empty, click "Start session →".
Expected: debate screen loads immediately (no spinner), first opponent turn behaves as before.

- [ ] **Step 3: Start a debate with a PDF attached**

Pick a small PDF (a few pages, with a clear factual claim in it), attach it on the topic screen, click "Start session →".
Expected: button shows "Indexing your document…", then transitions to the debate screen once indexing completes (should take well under a minute for a small PDF).

- [ ] **Step 4: Confirm the opponent cites the PDF**

Send a user argument related to the PDF's subject matter.
Expected: the opponent's response references specific content from the PDF (a fact, figure, or quote that isn't in the topic/description text alone).

- [ ] **Step 5: Confirm the source file is retrievable**

Run: `curl -H "Authorization: Bearer <token from localStorage dm_token>" http://localhost:8001/api/sessions/<session_id>/source-file`
Expected: `{"url": "http://localhost:9000/debatemind-sources/sources/<session_id>/<filename>?..."}`; fetching that URL in a browser downloads the original PDF.

- [ ] **Step 6: Confirm a failed index doesn't block the debate**

Stop the `minio` container (`docker compose stop minio`), attempt to start a session with a PDF attached.
Expected: upload fails (toast/error shown per Task 9 Step 3's `fileError` handling), but the debate still starts. Restart MinIO afterward: `docker compose start minio`.
