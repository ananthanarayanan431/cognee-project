import asyncio
import logging

from celery.signals import worker_init

from debatemind.config import settings
from debatemind.worker.celery_app import celery_app  # noqa: F401 — ensures tasks are registered

logger = logging.getLogger(__name__)


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
