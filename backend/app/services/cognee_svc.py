import cognee
from cognee.api.v1.search.search import SearchType
from app.config import settings
from app.agents.constants import PATTERN_TYPES

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
    """Persist one argument event into the user's permanent fingerprint graph."""
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
    """Return the user's top weakness patterns for opponent strategy loading."""
    results = await cognee.recall(
        f"top weakness patterns and fallacies for user {user_id}",
        query_type=SearchType.GRAPH_COMPLETION,
        datasets=[_dataset(user_id)],
        top_k=10,
    )
    # results is list[RecallResponse]; extract text
    return [{"text": getattr(r, "text", str(r))} for r in results]

async def improve_fingerprint(user_id: str, session_id: str) -> None:
    """Post-session: bridge session cache into permanent graph + reindex."""
    await cognee.improve(
        dataset=_dataset(user_id),
        session_ids=[session_id],
        build_global_context_index=True,
        run_in_background=True,
    )

async def forget_pattern(user_id: str, pattern_type: str) -> None:
    """Archive a mastered weakness node from the opponent's active strategy."""
    # Cognee forget operates on datasets; we remember the mastery event
    await cognee.remember(
        f"User: {user_id}\nPattern: {pattern_type}\nStatus: MASTERED\nAction: prune from opponent strategy",
        dataset_name=_dataset(user_id),
        run_in_background=True,
    )
