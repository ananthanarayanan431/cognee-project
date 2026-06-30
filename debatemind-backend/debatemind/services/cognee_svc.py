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
        f"Session: {session_id}\n"
        f"Topic: {topic}\n"
        f"Claim: {claim_text}\n"
        f"ArgumentPattern: {pattern_type}\n"
        f"Fallacy: {fallacy or 'None'}\n"
        f"Evidence: {evidence_quality}\n"
        f"Outcome: {outcome}\n"
    )
    dataset = _dataset(user_id)
    await cognee.add(text, dataset_name=dataset)
    await cognee.cognify(datasets=dataset)


async def recall_weaknesses(user_id: str) -> list[dict]:
    results = await cognee.search(
        query_text=f"top weakness patterns and fallacies for user {user_id}",
        query_type=SearchType.GRAPH_COMPLETION,
        datasets=[_dataset(user_id)],
        top_k=10,
    )
    return [{"text": r if isinstance(r, str) else getattr(r, "text", str(r))} for r in results]


async def improve_fingerprint(user_id: str, session_id: str) -> None:
    # cognee 0.1.40 has no separate "improve" step; re-cognifying the dataset
    # incorporates anything added since the last cognify call.
    await cognee.cognify(datasets=_dataset(user_id))


async def forget_pattern(user_id: str, pattern_type: str) -> None:
    # cognee has no forget primitive; mark the pattern as mastered so the
    # opponent stops targeting it.
    dataset = _dataset(user_id)
    text = (
        f"User: {user_id}\nPattern: {pattern_type}\n"
        "Status: MASTERED\nAction: prune from opponent strategy"
    )
    await cognee.add(text, dataset_name=dataset)
    await cognee.cognify(datasets=dataset)
