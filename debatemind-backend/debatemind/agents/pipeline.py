import asyncio
import logging

from langgraph.graph import END, StateGraph

from debatemind.agents.extractor import extract_argument
from debatemind.agents.judge import judge_exchange
from debatemind.agents.mastery import check_mastery
from debatemind.agents.opponent import (
    generate_opponent,
    invalidate_facts_cache,
    invalidate_weakness_cache,
)
from debatemind.agents.state import DebateState
from debatemind.cognee._base import ADD_TIMEOUT, COGNIFY_TIMEOUT
from debatemind.database import AsyncSessionLocal
from debatemind.services.user_facts_svc import record_user_facts
from debatemind.worker.tasks import (
    forget_pattern_task,
    remember_argument_task,
    remember_personal_fact_task,
)

logger = logging.getLogger(__name__)

# Generous upper bound on how long a dispatched remember task can take: cognee
# add() (up to ADD_TIMEOUT) followed by cognify() (up to COGNIFY_TIMEOUT).
_RESULT_TIMEOUT = ADD_TIMEOUT + COGNIFY_TIMEOUT


async def _await_and_invalidate(async_result, invalidate_fn, user_id: str, op_name: str) -> None:
    try:
        await asyncio.to_thread(async_result.get, timeout=_RESULT_TIMEOUT)
    except Exception:
        logger.exception("%s background task failed", op_name)
    # Invalidate regardless of outcome: on success the next turn should see
    # the fresh write immediately rather than up to an hour later; on
    # failure a retryable fresh recall is harmless.
    invalidate_fn(user_id)


async def _remember_facts_node(state: DebateState) -> DebateState:
    facts = state.get("personal_facts") or []
    if not facts:
        return state

    try:
        async with AsyncSessionLocal() as db:
            new_facts = await record_user_facts(db, state["user_id"], state["session_id"], facts)
    except Exception:
        logger.exception("record_user_facts failed for user %s — continuing", state["user_id"])
        return state

    for fact_text in new_facts:
        try:
            async_result = remember_personal_fact_task.delay(
                state["user_id"], state["session_id"], fact_text
            )
        except Exception:
            logger.exception(
                "remember_personal_fact dispatch failed for user %s — continuing",
                state["user_id"],
            )
            continue
        asyncio.create_task(
            _await_and_invalidate(
                async_result, invalidate_facts_cache, state["user_id"], "remember_personal_fact"
            )
        )
    return state


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

    try:
        async_result = remember_argument_task.delay(
            user_id=state["user_id"],
            session_id=state["session_id"],
            topic=state["topic"],
            claim_text=enriched_claim,
            pattern_type=state.get("extracted_pattern", "EvidenceBased"),
            fallacy=fallacy,
            evidence_quality=state.get("evidence_quality", "Moderate"),
            outcome=state.get("outcome", "Neutral"),
            reasoning=state.get("extracted_reasoning", "") or "",
            reasoning_approach=state.get("extracted_reasoning_approach"),
            cognitive_bias=state.get("extracted_cognitive_bias"),
        )
    except Exception:
        logger.exception(
            "remember_argument dispatch failed for user %s — continuing", state["user_id"]
        )
        return state
    asyncio.create_task(
        _await_and_invalidate(
            async_result, invalidate_weakness_cache, state["user_id"], "remember_argument"
        )
    )
    return state


async def _mastery_prune_node(state: DebateState) -> DebateState:
    for pattern in state.get("mastery_events", []):
        try:
            forget_pattern_task.delay(state["user_id"], pattern)
        except Exception:
            logger.exception(
                "forget_pattern dispatch failed for user %s pattern %s — continuing",
                state["user_id"],
                pattern,
            )
    return state


def _should_prune(state: DebateState) -> str:
    return "prune" if state.get("mastery_events") else END


graph = StateGraph(DebateState)
graph.add_node("extract", extract_argument)
graph.add_node("opponent", generate_opponent)
graph.add_node("judge", judge_exchange)
graph.add_node("mastery", check_mastery)
graph.add_node("remember", _remember_node)
graph.add_node("remember_facts", _remember_facts_node)
graph.add_node("prune", _mastery_prune_node)

graph.set_entry_point("extract")
graph.add_edge("extract", "opponent")
graph.add_edge("opponent", "judge")
graph.add_edge("judge", "mastery")
graph.add_edge("mastery", "remember")
graph.add_edge("remember", "remember_facts")
graph.add_conditional_edges("remember_facts", _should_prune, {"prune": "prune", END: END})
graph.add_edge("prune", END)

debate_pipeline = graph.compile()
