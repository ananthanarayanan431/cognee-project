# Cognee Background Worker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move every `cognee.add()`/`cognee.cognify()` write (currently fired via `asyncio.create_task`/`await` on the shared FastAPI event loop) into the existing dormant Celery worker, so a blocking dlt/psycopg2 pipeline run in one user's request can no longer freeze every other concurrent voice/chat/calibration user on the same process.

**Architecture:** Register real Celery tasks in the already-wired `debatemind/worker/tasks.py` (its `include=[...]` target and `worker_init` cognee-configuration hook already exist, just with zero tasks). Each task runs `asyncio.run(...)` on a `fingerprint.py`/new-service function inside a fresh worker process, which is safe because that process has its own event loop and its own `@lru_cache`d cognee relational engine — never the API process's. All five call sites (`voice_agent/tools.py`, `agents/pipeline.py` ×3, `routers/calibration.py`, `routers/sessions.py`) swap their `asyncio.create_task(...)`/`await ...` calls for `<task>.delay(...)`.

**Tech Stack:** Celery (already a pyproject dependency), Redis (already running via root `docker-compose.yml`, already the configured broker/backend in `celery_app.py`), pytest/pytest-asyncio (existing test suite).

## Global Constraints

- Every `.delay()` dispatch must be wrapped in `try/except Exception: logger.exception(...)` — a Redis-unreachable error must not crash the request/graph-node that triggered it, matching how failures were already swallowed before this change.
- No `await`ed cognee call may remain in `agents/pipeline.py`, `voice_agent/tools.py`, `routers/calibration.py`, or `routers/sessions.py` after this plan — every write goes through a Celery task.
- Preserve two specific behaviors during the swap: `_remember_node`/`_remember_facts_node`'s cache invalidation must still happen the moment the write lands (not on a fixed TTL only), and the existing summary-before-reindex ordering in `routers/sessions.py` must be preserved (and the equivalent race in `voice_agent/tools.py` fixed the same way).
- Read-only cognee calls (`recall_weaknesses`, `recall_topic_weaknesses`, `recall_user_facts` — `cognee.search()`, not the dlt ingestion path) are out of scope; do not touch them.
- `routers/sessions.py`'s `_write_title` background task is out of scope (no cognee call).

---

## Task 1: Extract the ordered fingerprint-finalize service

**Files:**
- Create: `debatemind/services/fingerprint_finalize_svc.py`
- Modify: `debatemind/routers/sessions.py:1-120` (remove `_write_chat_session_summary`, `_finalize_session_fingerprint`; update imports)
- Create: `tests/test_fingerprint_finalize_svc.py`

**Interfaces:**
- Produces: `async def write_chat_session_summary(user_id: str, session_id: str) -> None`, `async def finalize_session_fingerprint(user_id: str, session_id: str) -> None`, `async def finalize_voice_session_fingerprint(user_id: str, session_id: str, topic: str, difficulty: str, rounds_played: int, win_rate: float, weak_patterns: list[str], coaching_note: str = "") -> None` — all in `debatemind.services.fingerprint_finalize_svc`. Task 2 imports these.

Today `routers/sessions.py` defines `_finalize_session_fingerprint` (chat-only) inline and dispatches it via `asyncio.create_task`. Moving it to a service module lets `worker/tasks.py` (Task 2) import it without reaching into a router's private functions, and gives voice a matching ordered helper for the same race it currently has (`voice_agent/tools.py` fires summary and reindex as two independent, unordered tasks).

- [ ] **Step 1: Create the service module with the moved chat logic plus the new voice variant**

```python
# debatemind/services/fingerprint_finalize_svc.py
"""Ordered end-of-session fingerprint writes: summary first, then re-index.

Sequencing (rather than firing summary + reindex as independent background
tasks) guarantees the session summary is captured by the same consolidating
cognify pass that follows it — see finalize_session_fingerprint and
finalize_voice_session_fingerprint below.
"""

import logging
from collections import Counter

from sqlalchemy import select

from debatemind.cognee import improve_fingerprint, remember_session_summary
from debatemind.database import AsyncSessionLocal
from debatemind.models.session import DebateSession, Exchange

logger = logging.getLogger(__name__)


async def write_chat_session_summary(user_id: str, session_id: str) -> None:
    """Read completed session exchanges and write a summary to the Cognee fingerprint.

    Gives the AI cross-session topic-level context: win rate on this topic,
    average thinking-style scores, and which patterns were weak this session.
    """
    try:
        async with AsyncSessionLocal() as db:
            session_row = (
                await db.execute(select(DebateSession).where(DebateSession.id == session_id))
            ).scalar_one_or_none()
            if not session_row:
                return
            exchanges = (
                (await db.execute(select(Exchange).where(Exchange.session_id == session_id)))
                .scalars()
                .all()
            )

        if not exchanges:
            return

        total = len(exchanges)
        won = sum(1 for e in exchanges if e.outcome == "Won")
        win_rate = won / total

        logics = [e.judge_logic for e in exchanges if e.judge_logic is not None]
        evidences = [e.judge_evidence for e in exchanges if e.judge_evidence is not None]
        rhetorics = [e.judge_rhetoric for e in exchanges if e.judge_rhetoric is not None]
        avg_logic = sum(logics) / len(logics) if logics else 0.0
        avg_evidence = sum(evidences) / len(evidences) if evidences else 0.0
        avg_rhetoric = sum(rhetorics) / len(rhetorics) if rhetorics else 0.0

        weak_counts = Counter(
            e.detected_pattern for e in exchanges if e.detected_pattern and e.outcome != "Won"
        )
        weak_patterns = [p for p, _ in weak_counts.most_common(3)]

        await remember_session_summary(
            user_id=user_id,
            session_id=session_id,
            topic=session_row.topic,
            mode="chat",
            difficulty=session_row.difficulty,
            rounds_played=total,
            win_rate=win_rate,
            avg_logic=avg_logic,
            avg_evidence=avg_evidence,
            avg_rhetoric=avg_rhetoric,
            weak_patterns=weak_patterns,
        )
    except Exception:
        logger.exception(
            "remember_session_summary failed for user %s session %s", user_id, session_id
        )


async def finalize_session_fingerprint(user_id: str, session_id: str) -> None:
    """Ordered end-of-session fingerprint update: summary first, then re-index."""
    await write_chat_session_summary(user_id, session_id)
    await improve_fingerprint(user_id)


async def finalize_voice_session_fingerprint(
    user_id: str,
    session_id: str,
    topic: str,
    difficulty: str,
    rounds_played: int,
    win_rate: float,
    weak_patterns: list[str],
    coaching_note: str = "",
) -> None:
    """Ordered end-of-voice-session fingerprint update: summary first, then re-index."""
    await remember_session_summary(
        user_id=user_id,
        session_id=session_id,
        topic=topic,
        mode="voice",
        difficulty=difficulty,
        rounds_played=rounds_played,
        win_rate=win_rate,
        avg_logic=0.0,
        avg_evidence=0.0,
        avg_rhetoric=0.0,
        weak_patterns=weak_patterns,
        coaching_note=coaching_note,
    )
    await improve_fingerprint(user_id)
```

- [ ] **Step 2: Remove the moved functions from `routers/sessions.py` and update its imports**

In `debatemind/routers/sessions.py`, delete lines 51-119 (the `_write_chat_session_summary` and `_finalize_session_fingerprint` function bodies, including the blank lines directly around them), and change line 16 from:

```python
from debatemind.cognee import improve_fingerprint, remember_session_summary
```

to nothing (delete the line — neither name is used directly in this file anymore after Task 3 also removes the dispatch call). Leave a placeholder note here; Task 3 will add the replacement import (`from debatemind.worker.tasks import finalize_session_fingerprint_task`) when it rewires the dispatch call, so don't run the app in between these two steps.

- [ ] **Step 3: Write the regression tests for the moved and new logic**

```python
# tests/test_fingerprint_finalize_svc.py
"""Tests for debatemind.services.fingerprint_finalize_svc.

write_chat_session_summary is moved verbatim out of routers/sessions.py (which
had no direct test coverage of its stat computation); these tests lock in that
behavior. finalize_session_fingerprint / finalize_voice_session_fingerprint
tests verify the summary-before-reindex ordering the sessions.py code comment
has always relied on.
"""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from debatemind.database import Base
from debatemind.models.session import DebateSession, Exchange
from debatemind.services import fingerprint_finalize_svc as svc


@pytest.fixture
async def session_factory(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(svc, "AsyncSessionLocal", factory)
    yield factory
    await engine.dispose()


async def test_write_chat_session_summary_computes_win_rate_and_averages(
    session_factory, monkeypatch
):
    async with session_factory() as db:
        db.add(
            DebateSession(id="s1", user_id="u1", topic="AI Safety", difficulty="Hard")
        )
        db.add(
            Exchange(
                session_id="s1",
                turn_number=1,
                user_message="AI regulation is necessary",
                outcome="Won",
                judge_logic=8.0,
                judge_evidence=7.0,
                judge_rhetoric=6.0,
                detected_pattern=None,
            )
        )
        db.add(
            Exchange(
                session_id="s1",
                turn_number=2,
                user_message="but it should be minimal",
                outcome="Lost",
                judge_logic=4.0,
                judge_evidence=3.0,
                judge_rhetoric=5.0,
                detected_pattern="SlipperySlope",
            )
        )
        await db.commit()

    mock_summary = AsyncMock()
    monkeypatch.setattr(svc, "remember_session_summary", mock_summary)

    await svc.write_chat_session_summary("u1", "s1")

    mock_summary.assert_awaited_once()
    kwargs = mock_summary.call_args.kwargs
    assert kwargs["win_rate"] == 0.5
    assert kwargs["avg_logic"] == 6.0
    assert kwargs["weak_patterns"] == ["SlipperySlope"]


async def test_write_chat_session_summary_skips_missing_session(session_factory, monkeypatch):
    mock_summary = AsyncMock()
    monkeypatch.setattr(svc, "remember_session_summary", mock_summary)

    await svc.write_chat_session_summary("u1", "does-not-exist")

    mock_summary.assert_not_awaited()


async def test_finalize_session_fingerprint_writes_summary_before_reindex(monkeypatch):
    call_order = []

    async def track_summary(user_id, session_id):
        call_order.append("summary")

    async def track_reindex(user_id):
        call_order.append("reindex")

    monkeypatch.setattr(svc, "write_chat_session_summary", track_summary)
    monkeypatch.setattr(svc, "improve_fingerprint", track_reindex)

    await svc.finalize_session_fingerprint("u1", "s1")

    assert call_order == ["summary", "reindex"]


async def test_finalize_voice_session_fingerprint_writes_summary_before_reindex(monkeypatch):
    call_order = []

    async def track_summary(**kwargs):
        call_order.append("summary")

    async def track_reindex(user_id):
        call_order.append("reindex")

    monkeypatch.setattr(svc, "remember_session_summary", track_summary)
    monkeypatch.setattr(svc, "improve_fingerprint", track_reindex)

    await svc.finalize_voice_session_fingerprint(
        user_id="u1",
        session_id="s1",
        topic="AI Safety",
        difficulty="Hard",
        rounds_played=3,
        win_rate=0.7,
        weak_patterns=["Concession"],
        coaching_note="Good job",
    )

    assert call_order == ["summary", "reindex"]
```

- [ ] **Step 4: Run the new tests**

Run: `.venv/bin/pytest tests/test_fingerprint_finalize_svc.py -v`
Expected: 4 tests PASS.

- [ ] **Step 5: Run the full suite to confirm nothing else broke from removing the sessions.py functions**

Run: `.venv/bin/pytest -q`
Expected: All tests pass except any that directly reference `_write_chat_session_summary`/`_finalize_session_fingerprint` (there are none — confirmed no existing test imports them). If `routers/sessions.py` fails to import (e.g. leftover reference to the deleted import), fix before continuing.

- [ ] **Step 6: Commit**

```bash
git add debatemind/services/fingerprint_finalize_svc.py debatemind/routers/sessions.py tests/test_fingerprint_finalize_svc.py
git commit -m "refactor: extract ordered fingerprint-finalize logic into a service module"
```

---

## Task 2: Register the Celery tasks

**Files:**
- Modify: `debatemind/worker/tasks.py` (currently only the `worker_init` signal handler; add task definitions below it)
- Create: `tests/test_worker_tasks.py`

**Interfaces:**
- Consumes: `debatemind.services.fingerprint_finalize_svc.finalize_session_fingerprint`, `finalize_voice_session_fingerprint` (Task 1); `debatemind.cognee.remember_argument`, `remember_personal_fact`, `forget_pattern`, `improve_fingerprint` (existing, unchanged signatures).
- Produces: `remember_argument_task`, `remember_personal_fact_task`, `forget_pattern_task`, `improve_fingerprint_task`, `finalize_session_fingerprint_task`, `finalize_voice_session_fingerprint_task` — all Celery `Task` objects importable from `debatemind.worker.tasks`, each with a `.delay(...)` matching the wrapped function's parameter names. Tasks 3-6 import these.

`remember_session_summary` and `improve_fingerprint` are never called standalone anywhere in the codebase (every call site pairs them via the finalize functions), so they get no task of their own except `improve_fingerprint_task`, which is needed separately for `voice_agent/tools.py`'s "no debate_session" fallback path (Task 6).

- [ ] **Step 1: Add the six task definitions**

Append to `debatemind/worker/tasks.py` (after the existing `_configure_cognee` function, keeping the existing content above unchanged):

```python
@celery_app.task(name="debatemind.remember_argument")
def remember_argument_task(
    user_id: str,
    session_id: str,
    topic: str,
    claim_text: str,
    pattern_type: str,
    fallacy: str | None,
    evidence_quality: str,
    outcome: str,
    reasoning: str = "",
) -> None:
    from debatemind.cognee import remember_argument

    asyncio.run(
        remember_argument(
            user_id=user_id,
            session_id=session_id,
            topic=topic,
            claim_text=claim_text,
            pattern_type=pattern_type,
            fallacy=fallacy,
            evidence_quality=evidence_quality,
            outcome=outcome,
            reasoning=reasoning,
        )
    )


@celery_app.task(name="debatemind.remember_personal_fact")
def remember_personal_fact_task(user_id: str, session_id: str, fact_text: str) -> None:
    from debatemind.cognee import remember_personal_fact

    asyncio.run(remember_personal_fact(user_id, session_id, fact_text))


@celery_app.task(name="debatemind.forget_pattern")
def forget_pattern_task(user_id: str, pattern_type: str) -> None:
    from debatemind.cognee import forget_pattern

    asyncio.run(forget_pattern(user_id, pattern_type))


@celery_app.task(name="debatemind.improve_fingerprint")
def improve_fingerprint_task(user_id: str) -> None:
    from debatemind.cognee import improve_fingerprint

    asyncio.run(improve_fingerprint(user_id))


@celery_app.task(name="debatemind.finalize_session_fingerprint")
def finalize_session_fingerprint_task(user_id: str, session_id: str) -> None:
    from debatemind.services.fingerprint_finalize_svc import finalize_session_fingerprint

    asyncio.run(finalize_session_fingerprint(user_id, session_id))


@celery_app.task(name="debatemind.finalize_voice_session_fingerprint")
def finalize_voice_session_fingerprint_task(
    user_id: str,
    session_id: str,
    topic: str,
    difficulty: str,
    rounds_played: int,
    win_rate: float,
    weak_patterns: list[str],
    coaching_note: str = "",
) -> None:
    from debatemind.services.fingerprint_finalize_svc import (
        finalize_voice_session_fingerprint,
    )

    asyncio.run(
        finalize_voice_session_fingerprint(
            user_id=user_id,
            session_id=session_id,
            topic=topic,
            difficulty=difficulty,
            rounds_played=rounds_played,
            win_rate=win_rate,
            weak_patterns=weak_patterns,
            coaching_note=coaching_note,
        )
    )
```

- [ ] **Step 2: Write task tests**

Each task is called via `.run(...)` (executes the wrapped function directly, no broker needed) rather than `.delay()`, per Celery's standard unit-testing approach. These must be plain `def` tests, not `async def` — the task body calls `asyncio.run(...)` internally, which raises if called from inside an already-running event loop (pytest-asyncio's auto mode puts `async def` tests inside one).

```python
# tests/test_worker_tasks.py
"""Unit tests for debatemind.worker.tasks — verifies each Celery task invokes
the right underlying async function with the right arguments. Each task lazily
imports its target inside the function body, so we patch the target at its
source module (picked up at call time) and call `.run(...)` directly, which
executes the task body synchronously without a broker.
"""

from unittest.mock import AsyncMock

import debatemind.cognee as cognee_pkg
import debatemind.services.fingerprint_finalize_svc as finalize_svc
from debatemind.worker import tasks as worker_tasks


def test_remember_argument_task_calls_remember_argument(monkeypatch):
    mock = AsyncMock()
    monkeypatch.setattr(cognee_pkg, "remember_argument", mock)

    worker_tasks.remember_argument_task.run(
        user_id="u1",
        session_id="s1",
        topic="AI Safety",
        claim_text="claim",
        pattern_type="EvidenceBased",
        fallacy=None,
        evidence_quality="Strong",
        outcome="Won",
        reasoning="",
    )

    mock.assert_awaited_once_with(
        user_id="u1",
        session_id="s1",
        topic="AI Safety",
        claim_text="claim",
        pattern_type="EvidenceBased",
        fallacy=None,
        evidence_quality="Strong",
        outcome="Won",
        reasoning="",
    )


def test_remember_personal_fact_task_calls_remember_personal_fact(monkeypatch):
    mock = AsyncMock()
    monkeypatch.setattr(cognee_pkg, "remember_personal_fact", mock)

    worker_tasks.remember_personal_fact_task.run("u1", "s1", "likes chess")

    mock.assert_awaited_once_with("u1", "s1", "likes chess")


def test_forget_pattern_task_calls_forget_pattern(monkeypatch):
    mock = AsyncMock()
    monkeypatch.setattr(cognee_pkg, "forget_pattern", mock)

    worker_tasks.forget_pattern_task.run("u1", "AdHominem")

    mock.assert_awaited_once_with("u1", "AdHominem")


def test_improve_fingerprint_task_calls_improve_fingerprint(monkeypatch):
    mock = AsyncMock()
    monkeypatch.setattr(cognee_pkg, "improve_fingerprint", mock)

    worker_tasks.improve_fingerprint_task.run("u1")

    mock.assert_awaited_once_with("u1")


def test_finalize_session_fingerprint_task_calls_finalize_session_fingerprint(monkeypatch):
    mock = AsyncMock()
    monkeypatch.setattr(finalize_svc, "finalize_session_fingerprint", mock)

    worker_tasks.finalize_session_fingerprint_task.run("u1", "s1")

    mock.assert_awaited_once_with("u1", "s1")


def test_finalize_voice_session_fingerprint_task_calls_finalize_voice_session_fingerprint(
    monkeypatch,
):
    mock = AsyncMock()
    monkeypatch.setattr(finalize_svc, "finalize_voice_session_fingerprint", mock)

    worker_tasks.finalize_voice_session_fingerprint_task.run(
        user_id="u1",
        session_id="s1",
        topic="AI Safety",
        difficulty="Hard",
        rounds_played=3,
        win_rate=0.7,
        weak_patterns=["Concession"],
        coaching_note="Good job",
    )

    mock.assert_awaited_once_with(
        user_id="u1",
        session_id="s1",
        topic="AI Safety",
        difficulty="Hard",
        rounds_played=3,
        win_rate=0.7,
        weak_patterns=["Concession"],
        coaching_note="Good job",
    )
```

- [ ] **Step 3: Run the new tests**

Run: `.venv/bin/pytest tests/test_worker_tasks.py -v`
Expected: 6 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add debatemind/worker/tasks.py tests/test_worker_tasks.py
git commit -m "feat: register Celery tasks wrapping every cognee fingerprint write"
```

---

## Task 3: Rewire `routers/sessions.py` to dispatch via Celery

**Files:**
- Modify: `debatemind/routers/sessions.py` (import line removed in Task 1, dispatch call around what was line 553)

**Interfaces:**
- Consumes: `finalize_session_fingerprint_task` (Task 2).

- [ ] **Step 1: Add the import**

In `debatemind/routers/sessions.py`, where the `from debatemind.cognee import improve_fingerprint, remember_session_summary` line was removed in Task 1, add:

```python
from debatemind.worker.tasks import finalize_session_fingerprint_task
```

Keep it in the same alphabetically-sorted position among the existing `from debatemind....` imports (after `from debatemind.services.transcript_svc import format_transcript_text`, before `from debatemind.types import (`).

- [ ] **Step 2: Replace the dispatch call**

Find (originally around line 540-554, now shifted up by the ~70 lines removed in Task 1):

```python
    # Finalize the fingerprint in one ordered background task: write the
    # session summary first, THEN re-index. Running these as two independent
    # tasks (as before) let improve_fingerprint's cognify race ahead of the
    # summary write, so the summary could miss the current re-index pass.
    def _log_finalize_exc(task: asyncio.Task) -> None:
        if not task.cancelled() and task.exception():
            logger.error(
                "session fingerprint finalize failed for user %s session %s",
                user_id,
                session_id,
                exc_info=task.exception(),
            )

    finalize_task = asyncio.create_task(_finalize_session_fingerprint(user_id, session_id))
    finalize_task.add_done_callback(_log_finalize_exc)
```

Replace with:

```python
    # Finalize the fingerprint in one ordered Celery task: write the session
    # summary first, THEN re-index. A single task (rather than two independent
    # dispatches) guarantees the summary is captured before the consolidating
    # cognify pass — see fingerprint_finalize_svc.finalize_session_fingerprint.
    try:
        finalize_session_fingerprint_task.delay(user_id, session_id)
    except Exception:
        logger.exception(
            "finalize_session_fingerprint dispatch failed for user %s session %s",
            user_id,
            session_id,
        )
```

- [ ] **Step 3: Run the sessions router tests**

Run: `.venv/bin/pytest tests/test_sessions_router.py -v`
Expected: All PASS (no test currently asserts on `_finalize_session_fingerprint`/`finalize_task` internals, so this should be a clean pass — if any test does reference them, update it to assert `finalize_session_fingerprint_task.delay` was called instead).

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add debatemind/routers/sessions.py
git commit -m "refactor: dispatch session-end fingerprint finalize via Celery"
```

---

## Task 4: Rewire `routers/calibration.py` to dispatch via Celery

**Files:**
- Modify: `debatemind/routers/calibration.py`
- Modify: `tests/test_calibration_router.py`

**Interfaces:**
- Consumes: `remember_argument_task` (Task 2).

- [ ] **Step 1: Replace the import and remove the now-unused asyncio-task bookkeeping**

In `debatemind/routers/calibration.py`, replace lines 1-2 and 10:

```python
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from debatemind.agents.constants import CALIBRATION_TOPICS
from debatemind.agents.extractor import extract_argument
from debatemind.cognee import remember_argument
```

with:

```python
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from debatemind.agents.constants import CALIBRATION_TOPICS
from debatemind.agents.extractor import extract_argument
from debatemind.worker.tasks import remember_argument_task
```

Then delete the `_background_tasks` set and `_log_remember_exc` function entirely:

```python
# Keeps a strong reference to fire-and-forget tasks so the event loop's
# weak-referenced task set doesn't GC them mid-flight.
_background_tasks: set[asyncio.Task] = set()


def _log_remember_exc(task: asyncio.Task) -> None:
    _background_tasks.discard(task)
    if not task.cancelled() and task.exception():
        logger.error(
            "remember_argument (calibration) background task failed", exc_info=task.exception()
        )
```

(These aren't needed for Celery dispatch — `.delay()` doesn't return an `asyncio.Task`, so there's nothing to GC-protect or attach a done-callback to.)

- [ ] **Step 2: Replace the dispatch call**

Replace:

```python
    # Fire-and-forget: remember_argument runs add()+cognify() which can take many
    # seconds. Awaiting it inline would block the calibration response (and risk a
    # request timeout); background it so the user advances immediately.
    remember_task = asyncio.create_task(
        remember_argument(
            user_id=user_id,
            session_id=f"calibration_{user_id}",
            topic=topic,
            claim_text=body.text,
            pattern_type=state.get("extracted_pattern", "EvidenceBased"),
            fallacy=state.get("extracted_fallacy"),
            evidence_quality=state.get("evidence_quality", "Moderate"),
            outcome="Neutral",
            reasoning=state.get("extracted_reasoning", "") or "",
        )
    )
    _background_tasks.add(remember_task)
    remember_task.add_done_callback(_log_remember_exc)
```

with:

```python
    # Fire-and-forget via Celery: remember_argument runs add()+cognify() which
    # can take many seconds and, if run in-process, blocks every other
    # concurrent request on this server's event loop (dlt's sqlalchemy
    # destination opens a synchronous psycopg2 connection). Dispatch it to
    # the worker so the user advances immediately without freezing anyone else.
    try:
        remember_argument_task.delay(
            user_id=user_id,
            session_id=f"calibration_{user_id}",
            topic=topic,
            claim_text=body.text,
            pattern_type=state.get("extracted_pattern", "EvidenceBased"),
            fallacy=state.get("extracted_fallacy"),
            evidence_quality=state.get("evidence_quality", "Moderate"),
            outcome="Neutral",
            reasoning=state.get("extracted_reasoning", "") or "",
        )
    except Exception:
        logger.exception("remember_argument (calibration) dispatch failed for user %s", user_id)
```

- [ ] **Step 3: Update the test mock**

In `tests/test_calibration_router.py`, change the import line:

```python
from unittest.mock import AsyncMock
```

to:

```python
from unittest.mock import AsyncMock, MagicMock
```

and change:

```python
    monkeypatch.setattr(calibration_router, "remember_argument", AsyncMock())
```

to:

```python
    monkeypatch.setattr(calibration_router, "remember_argument_task", MagicMock())
```

- [ ] **Step 4: Run the calibration router tests**

Run: `.venv/bin/pytest tests/test_calibration_router.py -v`
Expected: All PASS.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add debatemind/routers/calibration.py tests/test_calibration_router.py
git commit -m "refactor: dispatch calibration remember_argument via Celery"
```

---

## Task 5: Rewire `agents/pipeline.py`'s three fingerprint nodes

**Files:**
- Modify: `debatemind/agents/pipeline.py`
- Modify: `tests/test_pipeline_mastery_prune.py`

**Interfaces:**
- Consumes: `remember_argument_task`, `remember_personal_fact_task`, `forget_pattern_task` (Task 2); `invalidate_weakness_cache`, `invalidate_facts_cache` (existing, unchanged, from `debatemind.agents.opponent`).

`_remember_node` and `_remember_facts_node` both need their done-callback's cache invalidation to still fire the moment the write completes (not just on the 1-hour TTL) — see `agents/opponent.py:19-26`. Since `.delay()` doesn't return an `asyncio.Task` with `add_done_callback`, replace that pattern with: dispatch via `.delay()` (fast, non-blocking), then a background `asyncio.create_task` that waits on the Celery `AsyncResult` via `asyncio.to_thread` (blocks a worker *thread*, not the event loop, and never touches cognee's loop-bound engine) and invalidates the cache once it resolves.

`_mastery_prune_node` doesn't invalidate any cache — the current code already just logs `forget_pattern` failures and continues (no retry bookkeeping to preserve), so this one is a direct swap.

- [ ] **Step 1: Update imports and add the shared wait-and-invalidate helper**

Replace the top of `debatemind/agents/pipeline.py` (imports through the `logger` line):

```python
import asyncio
import logging

from langgraph.graph import END, StateGraph

from debatemind.agents.extractor import extract_argument
from debatemind.agents.judge import judge_exchange
from debatemind.agents.mastery import check_mastery
from debatemind.agents.opponent import (
    generate_opponent,
    invalidate_facts_cache,
    invalidate_weakness_cache,
)
from debatemind.agents.state import DebateState
from debatemind.cognee import forget_pattern, remember_argument, remember_personal_fact
from debatemind.database import AsyncSessionLocal
from debatemind.services.user_facts_svc import record_user_facts

logger = logging.getLogger(__name__)
```

with:

```python
import asyncio
import logging

from langgraph.graph import END, StateGraph

from debatemind.agents.extractor import extract_argument
from debatemind.agents.judge import judge_exchange
from debatemind.agents.mastery import check_mastery
from debatemind.agents.opponent import (
    generate_opponent,
    invalidate_facts_cache,
    invalidate_weakness_cache,
)
from debatemind.agents.state import DebateState
from debatemind.cognee._base import ADD_TIMEOUT, COGNIFY_TIMEOUT
from debatemind.database import AsyncSessionLocal
from debatemind.services.user_facts_svc import record_user_facts
from debatemind.worker.tasks import (
    forget_pattern_task,
    remember_argument_task,
    remember_personal_fact_task,
)

logger = logging.getLogger(__name__)

# Generous upper bound on how long a dispatched remember task can take: cognee
# add() (up to ADD_TIMEOUT) followed by cognify() (up to COGNIFY_TIMEOUT).
_RESULT_TIMEOUT = ADD_TIMEOUT + COGNIFY_TIMEOUT


async def _await_and_invalidate(async_result, invalidate_fn, user_id: str, op_name: str) -> None:
    try:
        await asyncio.to_thread(async_result.get, timeout=_RESULT_TIMEOUT)
    except Exception:
        logger.exception("%s background task failed", op_name)
    # Invalidate regardless of outcome: on success the next turn should see
    # the fresh write immediately rather than up to an hour later; on
    # failure a retryable fresh recall is harmless.
    invalidate_fn(user_id)
```

- [ ] **Step 2: Rewire `_remember_facts_node`**

Replace:

```python
def _make_fact_remember_callback(user_id: str):
    def _callback(task: asyncio.Task) -> None:
        if not task.cancelled() and task.exception():
            logger.exception(
                "remember_personal_fact background task failed",
                exc_info=task.exception(),
            )
        invalidate_facts_cache(user_id)

    return _callback


async def _remember_facts_node(state: DebateState) -> DebateState:
    facts = state.get("personal_facts") or []
    if not facts:
        return state

    try:
        async with AsyncSessionLocal() as db:
            new_facts = await record_user_facts(db, state["user_id"], state["session_id"], facts)
    except Exception:
        logger.exception("record_user_facts failed for user %s — continuing", state["user_id"])
        return state

    for fact_text in new_facts:
        task = asyncio.create_task(
            remember_personal_fact(state["user_id"], state["session_id"], fact_text)
        )
        task.add_done_callback(_make_fact_remember_callback(state["user_id"]))
    return state
```

with:

```python
async def _remember_facts_node(state: DebateState) -> DebateState:
    facts = state.get("personal_facts") or []
    if not facts:
        return state

    try:
        async with AsyncSessionLocal() as db:
            new_facts = await record_user_facts(db, state["user_id"], state["session_id"], facts)
    except Exception:
        logger.exception("record_user_facts failed for user %s — continuing", state["user_id"])
        return state

    for fact_text in new_facts:
        try:
            async_result = remember_personal_fact_task.delay(
                state["user_id"], state["session_id"], fact_text
            )
        except Exception:
            logger.exception(
                "remember_personal_fact dispatch failed for user %s — continuing",
                state["user_id"],
            )
            continue
        asyncio.create_task(
            _await_and_invalidate(
                async_result, invalidate_facts_cache, state["user_id"], "remember_personal_fact"
            )
        )
    return state
```

- [ ] **Step 3: Rewire `_remember_node`**

Replace:

```python
def _make_remember_callback(user_id: str):
    def _callback(task: asyncio.Task) -> None:
        if not task.cancelled() and task.exception():
            logger.exception(
                "remember_argument background task failed",
                exc_info=task.exception(),
            )
        # Invalidate regardless of outcome: on success the next turn should see
        # the fresh write immediately rather than up to an hour later; on
        # failure a retryable fresh recall is harmless.
        invalidate_weakness_cache(user_id)

    return _callback


async def _remember_node(state: DebateState) -> DebateState:
    logic = state.get("judge_logic") or 0.0
    evidence = state.get("judge_evidence") or 0.0
    rhetoric = state.get("judge_rhetoric") or 0.0
    # Embed judge scores in the claim text so Cognee can semantically match on
    # thinking-style dimensions (e.g. "low evidence high rhetoric") when recalling.
    enriched_claim = (
        f"{state['user_message']} "
        f"[Scores — Logic:{logic:.1f} Evidence:{evidence:.1f} Rhetoric:{rhetoric:.1f}]"
    )
    # Prefer the judge's fallacy detection (post-response) over the extractor's
    # (pre-response); fall back to extractor if judge found nothing.
    fallacy = state.get("judge_fallacy") or state.get("extracted_fallacy")

    task = asyncio.create_task(
        remember_argument(
            user_id=state["user_id"],
            session_id=state["session_id"],
            topic=state["topic"],
            claim_text=enriched_claim,
            pattern_type=state.get("extracted_pattern", "EvidenceBased"),
            fallacy=fallacy,
            evidence_quality=state.get("evidence_quality", "Moderate"),
            outcome=state.get("outcome", "Neutral"),
            reasoning=state.get("extracted_reasoning", "") or "",
        )
    )
    task.add_done_callback(_make_remember_callback(state["user_id"]))
    return state
```

with:

```python
async def _remember_node(state: DebateState) -> DebateState:
    logic = state.get("judge_logic") or 0.0
    evidence = state.get("judge_evidence") or 0.0
    rhetoric = state.get("judge_rhetoric") or 0.0
    # Embed judge scores in the claim text so Cognee can semantically match on
    # thinking-style dimensions (e.g. "low evidence high rhetoric") when recalling.
    enriched_claim = (
        f"{state['user_message']} "
        f"[Scores — Logic:{logic:.1f} Evidence:{evidence:.1f} Rhetoric:{rhetoric:.1f}]"
    )
    # Prefer the judge's fallacy detection (post-response) over the extractor's
    # (pre-response); fall back to extractor if judge found nothing.
    fallacy = state.get("judge_fallacy") or state.get("extracted_fallacy")

    try:
        async_result = remember_argument_task.delay(
            user_id=state["user_id"],
            session_id=state["session_id"],
            topic=state["topic"],
            claim_text=enriched_claim,
            pattern_type=state.get("extracted_pattern", "EvidenceBased"),
            fallacy=fallacy,
            evidence_quality=state.get("evidence_quality", "Moderate"),
            outcome=state.get("outcome", "Neutral"),
            reasoning=state.get("extracted_reasoning", "") or "",
        )
    except Exception:
        logger.exception("remember_argument dispatch failed for user %s", state["user_id"])
        return state
    asyncio.create_task(
        _await_and_invalidate(
            async_result, invalidate_weakness_cache, state["user_id"], "remember_argument"
        )
    )
    return state
```

- [ ] **Step 4: Rewire `_mastery_prune_node`**

Replace:

```python
async def _mastery_prune_node(state: DebateState) -> DebateState:
    # `mastery_events` is read downstream (routers/sessions.py) to persist
    # MasteryLog rows and to notify the frontend. The Cognee write below is a
    # best-effort supplementary fact — Postgres is the source of truth for
    # gating (see get_active_mastered_patterns) — so a failure here must not
    # erase the achieved-mastery list, or the feature only ever "fires" when
    # Cognee happens to be down. Mirrors voice_agent/tools.py, which writes
    # MasteryLog unconditionally via a fire-and-forget forget_pattern task.
    for pattern in state.get("mastery_events", []):
        try:
            await forget_pattern(state["user_id"], pattern)
        except Exception:
            logger.exception(
                "forget_pattern failed for user %s pattern %s — continuing",
                state["user_id"],
                pattern,
            )
    return state
```

with:

```python
async def _mastery_prune_node(state: DebateState) -> DebateState:
    # `mastery_events` is read downstream (routers/sessions.py) to persist
    # MasteryLog rows and to notify the frontend. The Cognee write below is a
    # best-effort supplementary fact — Postgres is the source of truth for
    # gating (see get_active_mastered_patterns) — so a dispatch failure here
    # must not erase the achieved-mastery list, or the feature only ever
    # "fires" when Cognee happens to be down. Mirrors voice_agent/tools.py,
    # which writes MasteryLog unconditionally regardless of the dispatched
    # forget_pattern task's outcome.
    for pattern in state.get("mastery_events", []):
        try:
            forget_pattern_task.delay(state["user_id"], pattern)
        except Exception:
            logger.exception(
                "forget_pattern dispatch failed for user %s pattern %s — continuing",
                state["user_id"],
                pattern,
            )
    return state
```

- [ ] **Step 5: Update `tests/test_pipeline_mastery_prune.py`**

Replace the whole file:

```python
"""
Regression test for _mastery_prune_node: the same `mastery_events` state key
that check_mastery() populates with newly-achieved patterns is read downstream
by routers/sessions.py to persist MasteryLog rows and to notify the frontend
("mastery": [...] in the judge payload). _mastery_prune_node must not repurpose
that key to mean "patterns whose forget_pattern dispatch failed" — doing so
erases the achieved-mastery signal on the (common) success path.
"""

from unittest.mock import MagicMock, patch

from debatemind.agents import pipeline


async def test_successful_forget_pattern_dispatch_preserves_mastery_events():
    state = {"user_id": "u1", "mastery_events": ["AdHominem"]}
    mock_task = MagicMock()

    with patch.object(pipeline, "forget_pattern_task", mock_task):
        result = await pipeline._mastery_prune_node(state)

    mock_task.delay.assert_called_once_with("u1", "AdHominem")
    assert result["mastery_events"] == ["AdHominem"]


async def test_failed_forget_pattern_dispatch_still_preserves_mastery_events():
    """A dispatch failure (e.g. Redis unreachable) must not gate Postgres persistence.

    MasteryLog (the source of truth used by get_active_mastered_patterns) is
    written from this same list downstream — mirroring voice_agent/tools.py,
    which writes MasteryLog unconditionally regardless of the dispatched
    forget_pattern task's outcome.
    """
    state = {"user_id": "u1", "mastery_events": ["AdHominem"]}
    mock_task = MagicMock()
    mock_task.delay.side_effect = RuntimeError("boom")

    with patch.object(pipeline, "forget_pattern_task", mock_task):
        result = await pipeline._mastery_prune_node(state)

    assert result["mastery_events"] == ["AdHominem"]
```

- [ ] **Step 6: Run the pipeline tests**

Run: `.venv/bin/pytest tests/test_pipeline_mastery_prune.py -v`
Expected: 2 tests PASS.

- [ ] **Step 7: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: All PASS. Pay particular attention to `tests/test_opponent.py` (uses `invalidate_weakness_cache`/`invalidate_facts_cache`, unchanged) and any pipeline-level integration tests.

- [ ] **Step 8: Commit**

```bash
git add debatemind/agents/pipeline.py tests/test_pipeline_mastery_prune.py
git commit -m "refactor: dispatch chat pipeline fingerprint writes via Celery"
```

---

## Task 6: Rewire `voice_agent/tools.py`'s four dispatch points

**Files:**
- Modify: `debatemind/voice_agent/tools.py`

**Interfaces:**
- Consumes: `remember_argument_task`, `forget_pattern_task`, `improve_fingerprint_task`, `finalize_voice_session_fingerprint_task` (Task 2).

No cache invalidation to preserve here (voice tools don't read `_weakness_cache`), so every dispatch becomes a simple `try/except`-wrapped `.delay()` call via one small helper, no `asyncio.create_task`/thread-wait needed.

- [ ] **Step 1: Update imports and replace `_log_cognee_exc` with a dispatch helper**

Replace:

```python
from debatemind.cognee import (
    forget_pattern,
    improve_fingerprint,
    recall_topic_weaknesses,
    recall_weaknesses,
    remember_argument,
    remember_session_summary,
)
from debatemind.models.mastery import MasteryLog
from debatemind.models.session import DebateSession, Exchange
from debatemind.models.voice_session import VoiceSession, VoiceSessionNote
from debatemind.services.mastery_svc import get_active_mastered_patterns
```

with:

```python
from debatemind.cognee import recall_topic_weaknesses, recall_weaknesses
from debatemind.models.mastery import MasteryLog
from debatemind.models.session import DebateSession, Exchange
from debatemind.models.voice_session import VoiceSession, VoiceSessionNote
from debatemind.services.mastery_svc import get_active_mastered_patterns
from debatemind.worker.tasks import (
    finalize_voice_session_fingerprint_task,
    forget_pattern_task,
    improve_fingerprint_task,
    remember_argument_task,
)
```

Then replace:

```python
def _log_cognee_exc(task: asyncio.Task) -> None:
    if not task.cancelled() and task.exception():
        logger.exception(
            "cognee background task failed (voice)",
            exc_info=task.exception(),
        )
```

with:

```python
def _dispatch(task_fn, *args, op_name: str, **kwargs) -> None:
    try:
        task_fn.delay(*args, **kwargs)
    except Exception:
        logger.exception("%s dispatch failed (voice)", op_name)
```

- [ ] **Step 2: Rewire the `remember_argument` dispatch in `_save_debate_observation`**

Replace:

```python
        task = asyncio.create_task(
            remember_argument(
                user_id=user_id,
                session_id=debate_session_id,
                topic=topic,
                claim_text=content,
                pattern_type=pattern_type,
                fallacy=content if note_type == "fallacy" else None,
                evidence_quality=evidence_quality,
                outcome=outcome,
            )
        )
        task.add_done_callback(_log_cognee_exc)
```

with:

```python
        _dispatch(
            remember_argument_task,
            user_id=user_id,
            session_id=debate_session_id,
            topic=topic,
            claim_text=content,
            pattern_type=pattern_type,
            fallacy=content if note_type == "fallacy" else None,
            evidence_quality=evidence_quality,
            outcome=outcome,
            op_name="remember_argument",
        )
```

- [ ] **Step 3: Rewire the voice mastery `forget_pattern` dispatch**

Replace:

```python
                # 1. Cognee: mark pattern as mastered in the knowledge graph
                prune_task = asyncio.create_task(forget_pattern(user_id, pattern_type))
                prune_task.add_done_callback(_log_cognee_exc)
```

with:

```python
                # 1. Cognee: mark pattern as mastered in the knowledge graph
                _dispatch(forget_pattern_task, user_id, pattern_type, op_name="forget_pattern")
```

- [ ] **Step 4: Rewire the summary+reindex dispatch in `_end_voice_session`**

Replace:

```python
        summary_task = asyncio.create_task(
            remember_session_summary(
                user_id=user_id,
                session_id=debate_session_id,
                topic=debate_session.topic,
                mode="voice",
                difficulty=debate_session.difficulty,
                rounds_played=note_count,
                win_rate=voice_win_rate,
                avg_logic=0.0,
                avg_evidence=0.0,
                avg_rhetoric=0.0,
                weak_patterns=weak_patterns,
                coaching_note=closing_summary,
            )
        )
        summary_task.add_done_callback(_log_cognee_exc)

    # Re-index the fingerprint after all voice observations and summary are written.
    improve_task = asyncio.create_task(improve_fingerprint(user_id))
    improve_task.add_done_callback(_log_cognee_exc)
```

with:

```python
        # Ordered: write the summary before re-indexing, in one dispatched
        # task, so the summary is captured by the same consolidating cognify
        # pass (previously these were two independent, unordered tasks).
        _dispatch(
            finalize_voice_session_fingerprint_task,
            user_id=user_id,
            session_id=debate_session_id,
            topic=debate_session.topic,
            difficulty=debate_session.difficulty,
            rounds_played=note_count,
            win_rate=voice_win_rate,
            weak_patterns=weak_patterns,
            coaching_note=closing_summary,
            op_name="finalize_voice_session_fingerprint",
        )
    else:
        # No debate session to summarize, but still re-index any observations
        # already written during the session.
        _dispatch(improve_fingerprint_task, user_id, op_name="improve_fingerprint")
```

Note this moves the reindex dispatch inside the `if debate_session:` / new `else:` — previously `improve_task` ran unconditionally after the `if debate_session:` block. This preserves the exact same net behavior (reindex always happens exactly once either way) while fixing the ordering race for the common case.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: All PASS. There is no dedicated `voice_agent/tools.py` test file today (confirmed via search), so this step is the only automated check — rely on Task 7's manual smoke test for end-to-end coverage of these paths.

- [ ] **Step 6: Commit**

```bash
git add debatemind/voice_agent/tools.py
git commit -m "refactor: dispatch voice fingerprint writes via Celery, fix summary/reindex ordering"
```

---

## Task 7: Document the cloud worker deployment

**Files:**
- Modify: `debatemind/worker/celery_app.py` (add a module docstring)

**Interfaces:**
- None — this is a documentation-only step, no new interfaces.

The API's `Dockerfile` needs no change: `celery[redis]` is already a `pyproject.toml` dependency, so the image already has everything needed to run the worker command — it's just never invoked. Locally, `make dev`/`make start` already runs `celery -A debatemind.worker.celery_app worker` alongside the API (`Makefile:9-10,13,29-30`), so local dev needs no change either. The only gap is that nothing documents how to run the worker as a second process once this deploys to an actual cloud host (which the earlier design conversation left unspecified/TBD-by-platform).

- [ ] **Step 1: Add a deployment docstring to `celery_app.py`**

At the top of `debatemind/worker/celery_app.py`, before the existing `from celery import Celery` line, add:

```python
"""Celery app for cognee fingerprint writes (see debatemind/worker/tasks.py).

Locally, `make dev` / `make start` already runs this worker alongside the API
(see the Makefile's `celery`/`dev`/`start` targets) — no extra setup needed.

For a cloud deployment: this worker must run as a SECOND process from the
same image as the API (the Dockerfile needs no changes — celery[redis] is
already an installed dependency). Point the platform's second service/process
at the same image with this start command instead of the API's default CMD:

    celery -A debatemind.worker.celery_app worker --loglevel=info --concurrency=2

Give it the same environment variables as the API service — in particular
REDIS_URL (the broker/backend, must point at the same Redis both processes
share) and every COGNEE_*/OPENAI_*/OPENROUTER_* variable configure_cognee()
reads, since @worker_init.connect below configures cognee independently in
this process, never sharing state with the API process's cognee engine.
"""
```

- [ ] **Step 2: Verify the file still imports cleanly**

Run: `.venv/bin/python -c "from debatemind.worker.celery_app import celery_app; print(celery_app.conf.broker_url)"`
Expected: prints the configured Redis URL, no errors.

- [ ] **Step 3: Commit**

```bash
git add debatemind/worker/celery_app.py
git commit -m "docs: document the cloud worker deployment command"
```

---

## Task 8: End-to-end manual verification

**Files:** none (verification only).

- [ ] **Step 1: Run the full automated suite one more time**

Run: `.venv/bin/pytest -q`
Expected: All PASS.

- [ ] **Step 2: Confirm nothing still imports the removed symbols**

Run: `grep -rn "asyncio.create_task(remember_argument\|asyncio.create_task(forget_pattern\|asyncio.create_task(remember_session_summary\|asyncio.create_task(improve_fingerprint\|asyncio.create_task(remember_personal_fact" debatemind/`
Expected: no output (empty).

- [ ] **Step 3: Start infra + backend + worker locally**

Run: `make infra-up && make start`
Expected: Postgres, cognee-db, Redis, Neo4j containers healthy; backend on `:8001`; Celery worker log line `celery@<host> ready.`

- [ ] **Step 4: Smoke-test a dispatched task actually executes**

With the stack from Step 3 running, in a separate shell:

```bash
.venv/bin/python -c "
from debatemind.worker.tasks import remember_argument_task
r = remember_argument_task.delay(
    user_id='smoke-test-user',
    session_id='smoke-test-session',
    topic='Smoke Test',
    claim_text='This is a smoke test claim.',
    pattern_type='EvidenceBased',
    fallacy=None,
    evidence_quality='Moderate',
    outcome='Neutral',
    reasoning='',
)
print('dispatched, task id:', r.id)
print('result:', r.get(timeout=120))
"
```

Expected: prints a task id, then `result: None` once the worker finishes (may take up to ~2 minutes for `add()+cognify()`). Check the worker's terminal output for `cognee.add start` / `cognee.cognify ok` log lines confirming it actually ran in the worker process, not the API process.

- [ ] **Step 5: Confirm the API event loop stays responsive during that dispatched task**

While Step 4's task is still running (before `.get()` returns), in a third shell:

```bash
curl -w "\n%{time_total}s\n" http://localhost:8001/health
```

Expected: fast response (well under a second) — proof the API process wasn't blocked by the worker's in-flight cognee write, which is the entire point of this plan.
