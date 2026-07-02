# Debate concept (topic + description) and source PDF grounding

**Date:** 2026-06-30
**Status:** Approved

## Context

Today a debate session starts from a single one-line `topic` string
(`TopicSelection.tsx` → `POST /sessions/start` with `{topic, difficulty,
user_position}`). There's no way to add framing context beyond the topic
itself, and no way to ground the debate in a real source document. The user
wants:

1. A "concept" — topic plus a short free-text description — as the primary
   way to define what's being debated (always required, replaces the
   bare-topic-only flow).
2. An *additive*, optional PDF upload as supporting source material. When
   present, the opponent agent should cite real content from it rather than
   arguing in the abstract.
3. The uploaded PDF stored for reference, retrievable via a URL.
4. Cognee's `add()` → `cognify()` → `search()` pipeline (already embedded in
   this codebase via `cognee_svc.py`, see
   [[2026-06-30-cognee-local-cloud-mode-design]]) used to actually index and
   query the PDF, rather than building separate PDF-parsing/RAG machinery.

PDF storage uses MinIO (S3-compatible, self-hosted), matching the project's
existing local-first, docker-compose-based infra
(`debatemind-db` + `cognee-db` already run this way).

Scope decisions made during design:
- The PDF is **additive** to the topic+description concept, never a
  replacement for it.
- Source grounding is used by the **opponent only**; judge scoring is
  unchanged.
- Indexing is **synchronous**: the upload endpoint blocks until
  `cognee.cognify()` completes, and the frontend shows a spinner. No
  background-job/polling infrastructure needed.

## Design

### 1. Data model (`debatemind/models/session.py`)

Add three nullable columns to `DebateSession`:

```python
description: Mapped[str] = mapped_column(Text, nullable=True)
source_filename: Mapped[str] = mapped_column(String, nullable=True)
source_object_key: Mapped[str] = mapped_column(String, nullable=True)
```

`source_object_key` is `None` until a PDF is successfully indexed — its
presence is the single source of truth for "this session has a grounding
document." The Cognee dataset name is derived (`f"session_{id}_source"`),
not stored. New Alembic migration adds the three columns.

### 2. Storage layer — MinIO (`debatemind/services/storage_svc.py`, new file)

Thin wrapper around the `minio` SDK:

```python
def upload_source(session_id: str, filename: str, fileobj) -> str:
    """Puts the file at sources/{session_id}/{filename}, returns the object key."""

def get_source_url(object_key: str) -> str:
    """Presigned GET URL, 7-day expiry (MinIO's max)."""

def download_to_tempfile(object_key: str) -> Path:
    """Pulls the object to a local temp path — cognee.add() needs a filesystem
    path, not a stream."""
```

Bucket `debatemind-sources`, created on startup if missing (mirrors how
`main.py` already wires up Cognee config at lifespan startup).

Infra:
- `docker-compose.yml`: new `minio` service (`minio/minio:latest`, API port
  `9000`, console port `9001`, named volume `minio_data`), command
  `server /data --console-address ":9001"`, env `MINIO_ROOT_USER` /
  `MINIO_ROOT_PASSWORD`.
- `config.py` `Settings` gains `minio_endpoint`, `minio_access_key`,
  `minio_secret_key`, `minio_bucket` (default `"debatemind-sources"`),
  `minio_secure: bool = False`.
- `pyproject.toml`: add `minio` dependency.
- `.env.example`: matching `MINIO_*` defaults that work with zero edits
  against the compose service, same pattern as the existing `COGNEE_DB_*`
  vars.

### 3. Cognee ingestion — per-session source dataset (`cognee_svc.py`)

New functions, parallel to the existing per-user fingerprint functions but
scoped per-session:

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

`SearchType.CHUNKS` (raw relevant passages) is used instead of
`GRAPH_COMPLETION` — the opponent needs quotable source material to weave
into its own argument, not a pre-synthesized answer. The `try/except` in
`recall_source_context` is the normal "no PDF attached" path: most sessions
have no `session_{id}_source` dataset, and Cognee raises on a missing
dataset rather than returning an empty result set.

### 4. Backend API

`schemas/session.py`:
- `SessionStartIn` gains `description: str = ""`.
- `SessionOut` gains `description: str` and `has_source: bool = False`.

`routers/sessions.py`:
- `POST /sessions/start` — persists `description` alongside `topic`;
  unchanged otherwise.
- **New** `POST /sessions/{id}/source` — multipart `UploadFile`. Validates
  session ownership, `content_type == "application/pdf"` (400 otherwise),
  and size ≤ 20MB (413 otherwise). Flow:
  `storage_svc.upload_source()` → `storage_svc.download_to_tempfile()` →
  `cognee_svc.index_source_document()` (awaited) → delete the temp file →
  persist `source_filename` / `source_object_key` on the session row →
  return `{status: "indexed", source_filename}`. Round-tripping through
  MinIO before handing Cognee a local path (rather than indexing the
  upload's temp path directly) keeps the durable copy and the indexed copy
  guaranteed identical, and avoids ever trusting a client-supplied
  filesystem path.
  If indexing raises, the exception is caught, logged, and a 500 is
  returned, but the MinIO upload is **not** rolled back and
  `source_object_key` is left unset — the debate can still proceed without
  grounding; a failed index must never block starting the debate.
- **New** `GET /sessions/{id}/source-file` — 404 if `source_object_key` is
  unset, else returns `{url: storage_svc.get_source_url(...)}`. Generated
  fresh per request rather than stored, since presigned URLs expire.

### 5. Pipeline / opponent grounding

- `DebateState` (`agents/state.py`) gains `has_source: bool` and
  `source_context: list[dict]`.
- `routers/sessions.py:send_message` sets
  `has_source=bool(session.source_object_key)` when building
  `initial_state`.
- `agents/opponent.py`: when `state["has_source"]` is true, call
  `recall_source_context(session_id, state["user_message"])` before
  building the prompt. This is a per-query call (unlike the existing
  `_weakness_cache`, which is cached once per user) since relevant source
  passages depend on what the user just argued. Skipped entirely when
  `has_source` is false, so the no-PDF path costs nothing extra.
- `prompts/opponent.py`: `opponent_system_prompt` gains an optional
  `source_text` param; when non-empty, appends:
  ```
  Source material the user provided (cite specifics from this when relevant):
  {source_text}
  ```
- `description` flows into both `opponent_user_message(topic, description,
  user_argument)` and the extractor prompt as framing context — it's a
  prompt input, not a new pipeline node or state-machine branch.

Judge (`agents/judge.py`) is unchanged — per the "opponent only" scope
decision, evidence-quality scoring doesn't cross-check the source document.

### 6. Frontend (`frontend/src`)

`TopicSelection.tsx`:
- Description `<textarea>` under the topic input ("Add context — what's the
  angle, what should the opponent know?"), always visible, optional.
- PDF file picker (`accept="application/pdf"`, client-side 20MB check
  mirroring the backend limit) with selected filename shown and a remove
  (✕) control.
- `start()`: call `startSession(topic, description, difficulty, position)` →
  if a file is staged, set local `indexing = true`, call
  `uploadSource(sessionId, file)`, then call `setSession(...)` only after
  it resolves — blocking flow per the approved UX choice. Spinner copy:
  "Indexing your document…". On upload/indexing failure, show a toast but
  still call `setSession(...)` (matches the backend's "never block the
  debate" behavior).

`lib/api.ts`:
- `startSession` gains a `description` param.
- New `uploadSource(sessionId, file)` — builds `FormData` and POSTs
  directly with `fetch` (bypasses the JSON-only `apiFetch` helper, which
  always sets `Content-Type: application/json`).

`types/index.ts`: `SessionConfig` gains `description`.

## Out of scope

- Judge cross-checking user evidence claims against the source document
  (explicitly declined — opponent-only grounding for this iteration).
- Multiple source documents per session (one PDF, replaces any previous one
  on re-upload — re-upload behavior itself is out of scope too; first
  upload wins for now).
- Background/async indexing with polling (explicitly declined in favor of
  the simpler blocking-spinner flow).
- Non-PDF source files (images, docx, etc.) — Cognee supports them, but the
  upload endpoint validates `application/pdf` only for this iteration.
- Public/permanent MinIO URLs or bucket policies — presigned URLs only.

## Testing

- Unit-level: `cognee_svc.index_source_document` /
  `recall_source_context` against the local Cognee backend (real SDK calls,
  per the existing test pattern in this codebase) — confirm a PDF indexes
  and a relevant query returns chunk text; confirm `recall_source_context`
  returns `[]` for a session with no dataset instead of raising.
- Unit-level: `storage_svc` round-trip (`upload_source` →
  `download_to_tempfile` byte-for-byte match; `get_source_url` returns a
  fetchable URL) against a local MinIO container.
- API-level: `POST /sessions/{id}/source` with a non-PDF file → 400; with
  an oversized file → 413; with a valid PDF → 200 and session row updated.
- Manual: `docker compose up -d` (now including `minio`), start a session
  with topic+description+PDF, confirm the spinner resolves, confirm the
  opponent's first response references content from the uploaded PDF,
  confirm `GET /sessions/{id}/source-file` returns a working download URL.
