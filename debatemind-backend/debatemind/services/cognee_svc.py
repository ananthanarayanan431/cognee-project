import cognee
from cognee.api.v1.search.search import SearchType


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
        f"Topic: {topic}\n"
        f"Claim: {claim_text}\n"
        f"ArgumentPattern: {pattern_type}\n"
        f"Fallacy: {fallacy or 'None'}\n"
        f"Evidence: {evidence_quality}\n"
        f"Outcome: {outcome}\n"
    )
    await cognee.remember(
        text,
        dataset_name=_dataset(user_id),
        session_id=session_id,
        run_in_background=True,
        self_improvement=True,
    )


async def recall_weaknesses(user_id: str) -> list[dict]:
    results = await cognee.recall(
        f"top weakness patterns and fallacies for user {user_id}",
        query_type=SearchType.GRAPH_COMPLETION,
        datasets=[_dataset(user_id)],
        top_k=10,
    )
    return [{"text": getattr(r, "text", str(r))} for r in results]


async def improve_fingerprint(user_id: str, session_id: str) -> None:
    await cognee.improve(
        dataset=_dataset(user_id),
        session_ids=[session_id],
        build_global_context_index=True,
        run_in_background=True,
    )


async def forget_pattern(user_id: str, pattern_type: str) -> None:
    # Cognee forget operates on datasets; we mark the pattern as mastered
    # so the opponent stops targeting it.
    await cognee.remember(
        (
            f"User: {user_id}\nPattern: {pattern_type}\n"
            "Status: MASTERED\nAction: prune from opponent strategy"
        ),
        dataset_name=_dataset(user_id),
        run_in_background=True,
    )
