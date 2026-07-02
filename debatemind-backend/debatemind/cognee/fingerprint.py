"""User fingerprint operations.

Tracks each user's argumentation patterns, fallacies, and mastery state in the
cognee knowledge graph so the opponent and progress views can adapt over time.

Operations:
  remember_argument      — write a new argument record into the fingerprint
  recall_weaknesses      — read the top weakness/fallacy patterns for a user
  improve_fingerprint    — re-index the fingerprint after a batch of writes
  forget_pattern         — soft-delete: mark a pattern as MASTERED
  reactivate_pattern_fact — un-soft-delete: mark a pattern as REACTIVATED
"""

import asyncio
import logging
import time

import cognee
from cognee.api.v1.search.search import SearchType

from debatemind.cognee._base import (
    ADD_TIMEOUT,
    COGNIFY_TIMEOUT,
    SEARCH_TIMEOUT,
    elapsed_ms,
    fingerprint_dataset,
    preview,
    result_text,
)

logger = logging.getLogger(__name__)


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
    dataset = fingerprint_dataset(user_id)

    logger.info(
        "cognee.add start",
        extra={
            "event": "cognee.add.start",
            "operation": "remember_argument",
            "dataset": dataset,
            "user_id": user_id,
            "session_id": session_id,
            "content_length": len(text),
            "pattern_type": pattern_type,
            "fallacy": fallacy,
            "evidence_quality": evidence_quality,
            "outcome": outcome,
        },
    )
    t0 = time.monotonic()
    await asyncio.wait_for(cognee.add(text, dataset_name=dataset), timeout=ADD_TIMEOUT)
    logger.info(
        "cognee.add ok",
        extra={
            "event": "cognee.add.ok",
            "operation": "remember_argument",
            "dataset": dataset,
            "user_id": user_id,
            "content_length": len(text),
            "elapsed_ms": elapsed_ms(t0),
        },
    )

    logger.info(
        "cognee.cognify start",
        extra={
            "event": "cognee.cognify.start",
            "operation": "remember_argument",
            "dataset": dataset,
            "user_id": user_id,
        },
    )
    t0 = time.monotonic()
    await asyncio.wait_for(cognee.cognify(datasets=dataset), timeout=COGNIFY_TIMEOUT)
    logger.info(
        "cognee.cognify ok",
        extra={
            "event": "cognee.cognify.ok",
            "operation": "remember_argument",
            "dataset": dataset,
            "user_id": user_id,
            "elapsed_ms": elapsed_ms(t0),
        },
    )


async def recall_weaknesses(user_id: str) -> list[dict]:
    dataset = fingerprint_dataset(user_id)
    # Semantic query targets weakness-related chunks; user-ownership filter below
    # provides hard isolation because cognee's post-filter doesn't work for any
    # built-in retriever (none return "document_id" in their result dicts).
    query = "fallacy weak evidence poor argument outcome lost"
    user_marker = f"User: {user_id}"

    logger.info(
        "cognee.search start",
        extra={
            "event": "cognee.search.start",
            "operation": "recall_weaknesses",
            "dataset": dataset,
            "user_id": user_id,
            "query_type": "CHUNKS",
            "query": query,
            "top_k": 20,
        },
    )
    t0 = time.monotonic()
    try:
        results = await asyncio.wait_for(
            cognee.search(
                query_text=query,
                query_type=SearchType.CHUNKS,
                datasets=[dataset],
                top_k=20,
            ),
            timeout=SEARCH_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "cognee.search timeout",
            extra={
                "event": "cognee.search.timeout",
                "operation": "recall_weaknesses",
                "dataset": dataset,
                "user_id": user_id,
                "timeout_s": SEARCH_TIMEOUT,
                "elapsed_ms": elapsed_ms(t0),
            },
        )
        return []
    except Exception:
        logger.exception(
            "cognee.search error",
            extra={
                "event": "cognee.search.error",
                "operation": "recall_weaknesses",
                "dataset": dataset,
                "user_id": user_id,
                "elapsed_ms": elapsed_ms(t0),
            },
        )
        return []

    # Hard isolation: discard any chunk not tagged with this user's id.
    # Cognee's search() post-filter is ineffective (no retriever emits "document_id"),
    # so we enforce ownership here via the "User: <id>" marker in every stored record.
    items = [{"text": t} for r in results if user_marker in (t := result_text(r))][:10]
    logger.info(
        "cognee.search ok",
        extra={
            "event": "cognee.search.ok",
            "operation": "recall_weaknesses",
            "dataset": dataset,
            "user_id": user_id,
            "query_type": "CHUNKS",
            "results_raw": len(results),
            "results_filtered": len(items),
            "results_preview": [preview(it["text"], 120) for it in items[:3]],
            "elapsed_ms": elapsed_ms(t0),
        },
    )
    return items


async def improve_fingerprint(user_id: str) -> None:
    dataset = fingerprint_dataset(user_id)

    logger.info(
        "cognee.cognify start",
        extra={
            "event": "cognee.cognify.start",
            "operation": "improve_fingerprint",
            "dataset": dataset,
            "user_id": user_id,
        },
    )
    t0 = time.monotonic()
    await asyncio.wait_for(cognee.cognify(datasets=dataset), timeout=COGNIFY_TIMEOUT)
    logger.info(
        "cognee.cognify ok",
        extra={
            "event": "cognee.cognify.ok",
            "operation": "improve_fingerprint",
            "dataset": dataset,
            "user_id": user_id,
            "elapsed_ms": elapsed_ms(t0),
        },
    )


async def forget_pattern(user_id: str, pattern_type: str) -> None:
    dataset = fingerprint_dataset(user_id)
    text = (
        f"User: {user_id}\nPattern: {pattern_type}\n"
        "Status: MASTERED\nAction: prune from opponent strategy"
    )

    logger.info(
        "cognee.add start",
        extra={
            "event": "cognee.add.start",
            "operation": "forget_pattern",
            "dataset": dataset,
            "user_id": user_id,
            "pattern_type": pattern_type,
            "action": "mark_mastered",
            "content_length": len(text),
            "content_preview": preview(text),
        },
    )
    t0 = time.monotonic()
    await asyncio.wait_for(cognee.add(text, dataset_name=dataset), timeout=ADD_TIMEOUT)
    logger.info(
        "cognee.add ok",
        extra={
            "event": "cognee.add.ok",
            "operation": "forget_pattern",
            "dataset": dataset,
            "user_id": user_id,
            "pattern_type": pattern_type,
            "action": "mark_mastered",
            "content_length": len(text),
            "elapsed_ms": elapsed_ms(t0),
        },
    )

    logger.info(
        "cognee.cognify start",
        extra={
            "event": "cognee.cognify.start",
            "operation": "forget_pattern",
            "dataset": dataset,
            "user_id": user_id,
            "pattern_type": pattern_type,
        },
    )
    t0 = time.monotonic()
    await asyncio.wait_for(cognee.cognify(datasets=dataset), timeout=COGNIFY_TIMEOUT)
    logger.info(
        "cognee.cognify ok",
        extra={
            "event": "cognee.cognify.ok",
            "operation": "forget_pattern",
            "dataset": dataset,
            "user_id": user_id,
            "pattern_type": pattern_type,
            "elapsed_ms": elapsed_ms(t0),
        },
    )


async def reactivate_pattern_fact(user_id: str, pattern_type: str) -> None:
    dataset = fingerprint_dataset(user_id)
    text = (
        f"User: {user_id}\nPattern: {pattern_type}\n"
        "Status: REACTIVATED\nAction: resume targeting in opponent strategy"
    )

    logger.info(
        "cognee.add start",
        extra={
            "event": "cognee.add.start",
            "operation": "reactivate_pattern_fact",
            "dataset": dataset,
            "user_id": user_id,
            "pattern_type": pattern_type,
            "action": "reactivate",
            "content_length": len(text),
            "content_preview": preview(text),
        },
    )
    t0 = time.monotonic()
    await asyncio.wait_for(cognee.add(text, dataset_name=dataset), timeout=ADD_TIMEOUT)
    logger.info(
        "cognee.add ok",
        extra={
            "event": "cognee.add.ok",
            "operation": "reactivate_pattern_fact",
            "dataset": dataset,
            "user_id": user_id,
            "pattern_type": pattern_type,
            "action": "reactivate",
            "content_length": len(text),
            "elapsed_ms": elapsed_ms(t0),
        },
    )

    logger.info(
        "cognee.cognify start",
        extra={
            "event": "cognee.cognify.start",
            "operation": "reactivate_pattern_fact",
            "dataset": dataset,
            "user_id": user_id,
            "pattern_type": pattern_type,
        },
    )
    t0 = time.monotonic()
    await asyncio.wait_for(cognee.cognify(datasets=dataset), timeout=COGNIFY_TIMEOUT)
    logger.info(
        "cognee.cognify ok",
        extra={
            "event": "cognee.cognify.ok",
            "operation": "reactivate_pattern_fact",
            "dataset": dataset,
            "user_id": user_id,
            "pattern_type": pattern_type,
            "elapsed_ms": elapsed_ms(t0),
        },
    )
