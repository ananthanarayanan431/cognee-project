import logging

from langgraph.graph import END, StateGraph

from debatemind.agents.extractor import extract_argument
from debatemind.agents.judge import judge_exchange
from debatemind.agents.mastery import check_mastery
from debatemind.agents.opponent import generate_opponent
from debatemind.agents.state import DebateState
from debatemind.services.cognee_svc import forget_pattern, remember_argument

logger = logging.getLogger(__name__)


async def _remember_node(state: DebateState) -> DebateState:
    try:
        await remember_argument(
            user_id=state["user_id"],
            session_id=state["session_id"],
            topic=state["topic"],
            claim_text=state["user_message"],
            pattern_type=state.get("extracted_pattern", "EvidenceBased"),
            fallacy=state.get("extracted_fallacy"),
            evidence_quality=state.get("evidence_quality", "Moderate"),
            outcome=state.get("outcome", "Neutral"),
        )
    except Exception:
        logger.exception(
            "remember_argument failed for session %s — continuing", state["session_id"]
        )
    return state


async def _mastery_prune_node(state: DebateState) -> DebateState:
    for pattern in state.get("mastery_events", []):
        try:
            await forget_pattern(state["user_id"], pattern)
        except Exception:
            logger.exception(
                "forget_pattern failed for user %s pattern %s — continuing",
                state["user_id"],
                pattern,
            )
    # Clear mastery_events after processing so the next turn starts clean (Bug 1)
    state["mastery_events"] = []
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
