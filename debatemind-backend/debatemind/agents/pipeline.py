import asyncio
import logging

from langgraph.graph import END, StateGraph

from debatemind.agents.extractor import extract_argument
from debatemind.agents.judge import judge_exchange
from debatemind.agents.mastery import check_mastery
from debatemind.agents.opponent import generate_opponent, invalidate_weakness_cache
from debatemind.agents.state import DebateState
from debatemind.cognee import forget_pattern, remember_argument

logger = logging.getLogger(__name__)


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


async def _mastery_prune_node(state: DebateState) -> DebateState:
    failed = []
    for pattern in state.get("mastery_events", []):
        try:
            await forget_pattern(state["user_id"], pattern)
        except Exception:
            logger.exception(
                "forget_pattern failed for user %s pattern %s — continuing",
                state["user_id"],
                pattern,
            )
            failed.append(pattern)
    state["mastery_events"] = failed
    return state


def _should_prune(state: DebateState) -> str:
    return "prune" if state.get("mastery_events") else END


graph = StateGraph(DebateState)
graph.add_node("extract", extract_argument)
graph.add_node("opponent", generate_opponent)
graph.add_node("judge", judge_exchange)
graph.add_node("mastery", check_mastery)
graph.add_node("remember", _remember_node)
graph.add_node("prune", _mastery_prune_node)

graph.set_entry_point("extract")
graph.add_edge("extract", "opponent")
graph.add_edge("opponent", "judge")
graph.add_edge("judge", "mastery")
graph.add_edge("mastery", "remember")
graph.add_conditional_edges("remember", _should_prune, {"prune": "prune", END: END})
graph.add_edge("prune", END)

debate_pipeline = graph.compile()
