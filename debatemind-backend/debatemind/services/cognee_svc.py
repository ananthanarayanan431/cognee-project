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
    await asyncio.wait_for(cognee.cognify(datasets=_dataset(user_id)), timeout=COGNIFY_TIMEOUT)


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
    await asyncio.wait_for(cognee.add(file_path, dataset_name=dataset), timeout=ADD_TIMEOUT)
    await asyncio.wait_for(cognee.cognify(datasets=dataset), timeout=COGNIFY_TIMEOUT)


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
