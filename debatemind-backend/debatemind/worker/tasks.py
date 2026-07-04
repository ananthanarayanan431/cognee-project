import asyncio
import logging

from celery.signals import worker_init

from debatemind.config import settings
from debatemind.worker.celery_app import celery_app  # noqa: F401 — ensures tasks are registered

logger = logging.getLogger(__name__)


def _reset_cognee_async_engines() -> None:
    """Drop cognee's lru_cached async DB engines so this task rebuilds them on
    its own event loop.

    Every task runs a fresh asyncio.run() loop, but cognee caches its relational
    (asyncpg) and graph (neo4j async) engines process-globally via @lru_cache —
    and @worker_init creates them once in the PARENT process before Celery forks
    the children, so the children inherit engines bound to a loop they don't own.
    Reusing such an engine fails with "another operation is in progress" /
    "attached to a different loop", so only the first task per worker ever
    succeeded. Clearing the caches forces a fresh, correctly-bound engine for
    every task (first or not, freshly forked or not).
    """
    from cognee.infrastructure.databases.graph.get_graph_engine import create_graph_engine
    from cognee.infrastructure.databases.relational.create_relational_engine import (
        create_relational_engine,
    )

    create_relational_engine.cache_clear()
    create_graph_engine.cache_clear()
    try:
        from cognee.infrastructure.databases.vector.create_vector_engine import (
            create_vector_engine,
        )

        cache_clear = getattr(create_vector_engine, "cache_clear", None)
        if cache_clear:
            cache_clear()
    except Exception:
        logger.debug("vector engine cache clear skipped", exc_info=True)


def _reset_litellm_logging_worker() -> None:
    """Drop litellm's process-global async logging worker so this task rebuilds
    its queue on its own event loop.

    Same shape of bug as the cognee engines above: cognee calls litellm, whose
    GLOBAL_LOGGING_WORKER caches an asyncio.Queue bound to the first loop that
    ran it. Every task uses a fresh asyncio.run() loop, so from the second task
    on the worker's `await self._queue.get()` raises "<Queue> is bound to a
    different event loop" — an un-awaited background-task crash that spams the
    logs and silently drops litellm's success/cost callbacks. Clearing the
    singleton's queue/task forces a fresh, correctly-bound queue per task. Any
    callbacks still queued from the previous loop are best-effort and are dropped
    (they were already failing); no functional logging is lost.
    """
    try:
        from litellm.litellm_core_utils.logging_worker import GLOBAL_LOGGING_WORKER

        GLOBAL_LOGGING_WORKER._queue = None
        GLOBAL_LOGGING_WORKER._worker_task = None
    except Exception:
        logger.debug("litellm logging worker reset skipped", exc_info=True)


def _run_cognee(coro):
    """Run a cognee coroutine with freshly-bound engines (see reset helpers)."""
    _reset_cognee_async_engines()
    _reset_litellm_logging_worker()
    return asyncio.run(coro)


@worker_init.connect
def _configure_cognee(**kwargs):
    from cognee.modules.engine.operations.setup import setup as cognee_setup

    from debatemind.services.cognee_config import configure_cognee

    configure_cognee(settings)
    asyncio.run(cognee_setup())


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
    reasoning_approach: str | None = None,
    cognitive_bias: str | None = None,
) -> None:
    from debatemind.cognee import remember_argument

    _run_cognee(
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
            reasoning_approach=reasoning_approach,
            cognitive_bias=cognitive_bias,
        )
    )


@celery_app.task(name="debatemind.remember_personal_fact")
def remember_personal_fact_task(user_id: str, session_id: str, fact_text: str) -> None:
    from debatemind.cognee import remember_personal_fact

    _run_cognee(remember_personal_fact(user_id, session_id, fact_text))


@celery_app.task(name="debatemind.forget_pattern")
def forget_pattern_task(user_id: str, pattern_type: str) -> None:
    from debatemind.cognee import forget_pattern

    _run_cognee(forget_pattern(user_id, pattern_type))


@celery_app.task(name="debatemind.improve_fingerprint")
def improve_fingerprint_task(user_id: str) -> None:
    from debatemind.cognee import improve_fingerprint

    _run_cognee(improve_fingerprint(user_id))


@celery_app.task(name="debatemind.finalize_session_fingerprint")
def finalize_session_fingerprint_task(user_id: str, session_id: str) -> None:
    from debatemind.services.fingerprint_finalize_svc import finalize_session_fingerprint

    _run_cognee(finalize_session_fingerprint(user_id, session_id))


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

    _run_cognee(
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
