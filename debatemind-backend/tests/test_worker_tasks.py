"""Unit tests for debatemind.worker.tasks — verifies each Celery task invokes
the right underlying async function with the right arguments. Each task lazily
imports its target inside the function body, so we patch the target at its
source module (picked up at call time) and call `.run(...)` directly, which
executes the task body synchronously without a broker.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

import debatemind.cognee as cognee_pkg
import debatemind.services.fingerprint_finalize_svc as finalize_svc
from debatemind.worker import tasks as worker_tasks


async def _bind_worker_queue_to_current_loop():
    """Bind litellm's global logging-worker queue to the running loop. The queue
    only records its loop when an awaited get() finds it empty — exactly what the
    worker loop does — so we drive that path and let it time out."""
    from litellm.litellm_core_utils.logging_worker import GLOBAL_LOGGING_WORKER

    GLOBAL_LOGGING_WORKER._ensure_queue()
    try:
        await asyncio.wait_for(GLOBAL_LOGGING_WORKER._queue.get(), timeout=0.02)
    except asyncio.TimeoutError:
        pass


async def _drain_worker_queue():
    """Mirror litellm's worker start()+loop: ensure the queue exists (a no-op if
    it survived from a prior loop), then `await self._queue.get()` on an empty
    queue — the call that raises when the queue is bound to another loop."""
    from litellm.litellm_core_utils.logging_worker import GLOBAL_LOGGING_WORKER

    GLOBAL_LOGGING_WORKER._ensure_queue()
    await asyncio.wait_for(GLOBAL_LOGGING_WORKER._queue.get(), timeout=0.02)


def test_litellm_logging_worker_queue_rebinds_across_event_loops():
    """Repro for the "<Queue> is bound to a different event loop" spam: each
    Celery task runs a fresh asyncio.run() loop, but litellm's process-global
    logging worker caches its asyncio.Queue against the first loop. Without a
    per-task reset the second loop can't touch the queue.
    """
    from litellm.litellm_core_utils.logging_worker import GLOBAL_LOGGING_WORKER

    # Start from a pristine singleton.
    GLOBAL_LOGGING_WORKER._queue = None
    GLOBAL_LOGGING_WORKER._worker_task = None

    asyncio.run(_bind_worker_queue_to_current_loop())

    # Second task on a new loop, WITHOUT the reset → the stale queue rejects it.
    with pytest.raises(RuntimeError, match="different event loop"):
        asyncio.run(_drain_worker_queue())

    # A reset before each task gives every loop a fresh queue — no cross-loop error.
    worker_tasks._reset_litellm_logging_worker()
    asyncio.run(_bind_worker_queue_to_current_loop())
    worker_tasks._reset_litellm_logging_worker()
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(_drain_worker_queue())


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
        reasoning_approach=None,
        cognitive_bias=None,
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
