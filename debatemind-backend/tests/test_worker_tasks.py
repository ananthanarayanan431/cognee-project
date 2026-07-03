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
