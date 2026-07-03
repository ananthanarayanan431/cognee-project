"""User fingerprint operations.

Tracks each user's argumentation patterns, fallacies, and mastery state in the
cognee knowledge graph so the opponent and progress views can adapt over time.

Operations:
  remember_argument        — write a new argument record into the fingerprint
  remember_session_summary — write a session-level performance summary
  recall_weaknesses        — read top weakness/fallacy patterns (generic)
  recall_topic_weaknesses  — read weakness patterns for a specific topic
  improve_fingerprint      — re-index the fingerprint after a batch of writes
  forget_pattern           — soft-delete: mark a pattern as MASTERED
  reactivate_pattern_fact  — un-soft-delete: mark a pattern as REACTIVATED
"""

import asyncio
import logging
import time

import cognee
from cognee.api.v1.search.search import SearchType
from cognee.tasks.storage import add_data_points

from debatemind.cognee._base import (
    ADD_TIMEOUT,
    COGNIFY_TIMEOUT,
    SEARCH_TIMEOUT,
    elapsed_ms,
    filter_out_patterns,
    fingerprint_dataset,
    ontology_file,
    preview,
    result_text,
)
from debatemind.cognee.schema import (
    ArgumentRecord,
    PersonalFact,
    SessionSummary,
    Topic,
    UserProfile,
    topic_id,
    user_profile_id,
)

logger = logging.getLogger(__name__)


def _argument_summary(
    topic: str,
    pattern_type: str,
    fallacy: str | None,
    evidence_quality: str,
    outcome: str,
    reasoning: str,
) -> str:
    """A natural-language sentence describing the argument.

    The terse `key: value` markers alone give cognify's LLM extractor little to
    work with; a prose sentence that names the topic, pattern, evidence, and
    fallacy lets it link the argument to a KnowledgeDomain and type it against
    the ontology (ReasoningApproach / EvidenceType / Fallacy). The reasoning
    sentence, when present, is the richest signal for those wider node types.
    """
    fallacy_clause = f" and committed the {fallacy} fallacy" if fallacy else ""
    summary = (
        f'In a debate about "{topic}", the user made a {pattern_type} argument '
        f"with {evidence_quality} evidence{fallacy_clause}; the outcome was {outcome}."
    )
    if reasoning:
        summary += f" Reasoning: {reasoning}"
    return summary


async def remember_argument(
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
    if reasoning:
        text += f"Reasoning: {reasoning}\n"
    summary = _argument_summary(topic, pattern_type, fallacy, evidence_quality, outcome, reasoning)
    text += "Summary: " + summary + "\n"
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
    await asyncio.wait_for(
        cognee.cognify(datasets=dataset, ontology_file_path=ontology_file()),
        timeout=COGNIFY_TIMEOUT,
    )
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

    # Typed node: gives forget() a precise node to delete and the
    # knowledge-graph view a stable node to render, independent of what
    # cognify's LLM extraction infers from the prose above.
    try:
        owner = UserProfile(id=user_profile_id(user_id), user_id=user_id)
        topic_node = Topic(id=topic_id(user_id, topic), user_id=user_id, name=topic)
        record = ArgumentRecord(
            user_id=user_id,
            session_id=session_id,
            topic_name=topic,
            claim_text=claim_text,
            pattern_type=pattern_type,
            fallacy=fallacy,
            evidence_quality=evidence_quality,
            outcome=outcome,
            reasoning=reasoning,
            summary=summary,
            topic=topic_node,
            owner=owner,
        )
        await add_data_points([owner, topic_node, record])
    except Exception:
        logger.exception(
            "add_data_points failed for ArgumentRecord user %s — continuing "
            "(prose write above already succeeded; only the typed node is lost)",
            user_id,
        )


async def remember_session_summary(
    user_id: str,
    session_id: str,
    topic: str,
    mode: str,
    difficulty: str,
    rounds_played: int,
    win_rate: float,
    avg_logic: float,
    avg_evidence: float,
    avg_rhetoric: float,
    weak_patterns: list[str],
    coaching_note: str = "",
) -> None:
    """Write a session-level performance summary to the Cognee fingerprint.

    This gives the AI opponent cross-session topic-level context — e.g. "user
    wins 30% on AI regulation debates, weak on EvidenceBased reasoning there".
    """
    patterns_str = ", ".join(weak_patterns) if weak_patterns else "none"
    text = (
        f"User: {user_id}\n"
        f"Session: {session_id}\n"
        f"Topic: {topic}\n"
        f"Mode: {mode}\n"
        f"Difficulty: {difficulty}\n"
        f"RoundsPlayed: {rounds_played}\n"
        f"WinRate: {win_rate:.2f}\n"
        f"ThinkingStyle: Logic={avg_logic:.1f} Evidence={avg_evidence:.1f} "
        f"Rhetoric={avg_rhetoric:.1f}\n"
        f"WeakPatternsThisSession: {patterns_str}\n"
        f"Outcome: {'positive' if win_rate >= 0.5 else 'needs improvement'}\n"
    )
    if coaching_note:
        text += f"CoachingNote: {coaching_note}\n"
    # Prose sentence weaving topic (-> KnowledgeDomain), thinking style, and weak
    # patterns so cognify can extract domain-linked, typed nodes rather than
    # scoring the terse markers alone.
    summary = (
        f'Over {rounds_played} rounds debating "{topic}" in {mode} mode at '
        f"{difficulty} difficulty, the user won {win_rate:.0%} of exchanges. "
        f"Their thinking style leaned Logic {avg_logic:.1f}, Evidence {avg_evidence:.1f}, "
        f"Rhetoric {avg_rhetoric:.1f}. Recurring weak patterns: {patterns_str}."
    )
    text += "Summary: " + summary + "\n"

    dataset = fingerprint_dataset(user_id)

    logger.info(
        "cognee.add start",
        extra={
            "event": "cognee.add.start",
            "operation": "remember_session_summary",
            "dataset": dataset,
            "user_id": user_id,
            "session_id": session_id,
            "mode": mode,
            "topic": topic,
            "win_rate": win_rate,
            "content_length": len(text),
        },
    )
    t0 = time.monotonic()
    await asyncio.wait_for(cognee.add(text, dataset_name=dataset), timeout=ADD_TIMEOUT)
    logger.info(
        "cognee.add ok",
        extra={
            "event": "cognee.add.ok",
            "operation": "remember_session_summary",
            "dataset": dataset,
            "user_id": user_id,
            "elapsed_ms": elapsed_ms(t0),
        },
    )

    t0 = time.monotonic()
    await asyncio.wait_for(
        cognee.cognify(datasets=dataset, ontology_file_path=ontology_file()),
        timeout=COGNIFY_TIMEOUT,
    )
    logger.info(
        "cognee.cognify ok",
        extra={
            "event": "cognee.cognify.ok",
            "operation": "remember_session_summary",
            "dataset": dataset,
            "user_id": user_id,
            "elapsed_ms": elapsed_ms(t0),
        },
    )

    try:
        owner = UserProfile(id=user_profile_id(user_id), user_id=user_id)
        topic_node = Topic(id=topic_id(user_id, topic), user_id=user_id, name=topic)
        session_summary = SessionSummary(
            user_id=user_id,
            session_id=session_id,
            topic_name=topic,
            mode=mode,
            difficulty=difficulty,
            rounds_played=rounds_played,
            win_rate=win_rate,
            avg_logic=avg_logic,
            avg_evidence=avg_evidence,
            avg_rhetoric=avg_rhetoric,
            weak_patterns=weak_patterns,
            coaching_note=coaching_note,
            summary=summary,
            topic=topic_node,
            owner=owner,
        )
        await add_data_points([owner, topic_node, session_summary])
    except Exception:
        logger.exception("add_data_points failed for SessionSummary user %s — continuing", user_id)


async def remember_personal_fact(user_id: str, session_id: str, fact_text: str) -> None:
    """Write a personal fact the user revealed (name, likes, background) to Cognee.

    Kept as its own record type (Type: PersonalFact) so recall_user_facts can
    retrieve these independently of argument/weakness records.
    """
    text = (
        f"User: {user_id}\n"
        f"Session: {session_id}\n"
        "Type: PersonalFact\n"
        f"Fact: {fact_text}\n"
        f"Summary: The user shared a personal fact: {fact_text}\n"
    )
    dataset = fingerprint_dataset(user_id)

    logger.info(
        "cognee.add start",
        extra={
            "event": "cognee.add.start",
            "operation": "remember_personal_fact",
            "dataset": dataset,
            "user_id": user_id,
            "session_id": session_id,
            "content_length": len(text),
        },
    )
    t0 = time.monotonic()
    await asyncio.wait_for(cognee.add(text, dataset_name=dataset), timeout=ADD_TIMEOUT)
    logger.info(
        "cognee.add ok",
        extra={
            "event": "cognee.add.ok",
            "operation": "remember_personal_fact",
            "dataset": dataset,
            "user_id": user_id,
            "content_length": len(text),
            "elapsed_ms": elapsed_ms(t0),
        },
    )

    t0 = time.monotonic()
    await asyncio.wait_for(
        cognee.cognify(datasets=dataset, ontology_file_path=ontology_file()),
        timeout=COGNIFY_TIMEOUT,
    )
    logger.info(
        "cognee.cognify ok",
        extra={
            "event": "cognee.cognify.ok",
            "operation": "remember_personal_fact",
            "dataset": dataset,
            "user_id": user_id,
            "elapsed_ms": elapsed_ms(t0),
        },
    )

    try:
        owner = UserProfile(id=user_profile_id(user_id), user_id=user_id)
        fact = PersonalFact(
            user_id=user_id, session_id=session_id, fact_text=fact_text, owner=owner
        )
        await add_data_points([owner, fact])
    except Exception:
        logger.exception("add_data_points failed for PersonalFact user %s — continuing", user_id)


async def recall_user_facts(user_id: str, topic: str = "") -> list[dict]:
    """Read back personal facts previously shared by the user (name, likes, etc.).

    Used by the opponent to reference something the user revealed about
    themselves as a pointed, specific jab — scoped loosely to the current
    topic so the most relevant facts surface first, but not excluded if the
    connection is only found by the opponent's own reasoning downstream.
    """
    dataset = fingerprint_dataset(user_id)
    query = (
        f"personal facts about the user relevant to {topic}: "
        "preferences, background, interests, dislikes, occupation"
        if topic
        else "personal facts about the user: preferences, background, interests, dislikes"
    )
    user_marker = f"User: {user_id}"

    logger.info(
        "cognee.search start",
        extra={
            "event": "cognee.search.start",
            "operation": "recall_user_facts",
            "dataset": dataset,
            "user_id": user_id,
            "topic": topic,
            "query_type": "CHUNKS",
            "query": query,
            "top_k": 10,
        },
    )
    t0 = time.monotonic()
    try:
        results = await asyncio.wait_for(
            cognee.search(
                query_text=query,
                query_type=SearchType.CHUNKS,
                datasets=[dataset],
                top_k=10,
            ),
            timeout=SEARCH_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "cognee.search timeout",
            extra={
                "event": "cognee.search.timeout",
                "operation": "recall_user_facts",
                "dataset": dataset,
                "user_id": user_id,
                "elapsed_ms": elapsed_ms(t0),
            },
        )
        return []
    except Exception as e:
        if type(e).__name__ == "NoDataError":
            return []
        logger.exception(
            "cognee.search error",
            extra={
                "event": "cognee.search.error",
                "operation": "recall_user_facts",
                "dataset": dataset,
                "user_id": user_id,
                "elapsed_ms": elapsed_ms(t0),
            },
        )
        return []

    owned = [
        {"text": t}
        for r in results
        if f"{user_marker}\n" in (t := result_text(r)) and "Type: PersonalFact" in t
    ]
    logger.info(
        "cognee.search ok",
        extra={
            "event": "cognee.search.ok",
            "operation": "recall_user_facts",
            "dataset": dataset,
            "user_id": user_id,
            "results_raw": len(results),
            "results_owned": len(owned),
            "elapsed_ms": elapsed_ms(t0),
        },
    )
    return owned[:5]


async def recall_weaknesses(user_id: str, exclude_patterns: set[str] | None = None) -> list[dict]:
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
    except Exception as e:
        # Check by name to survive uvicorn hot-reload, which can cause NoDataError
        # class identity to diverge between fingerprint.py and the venv's chunks_retriever.
        if type(e).__name__ == "NoDataError":
            logger.warning(
                "cognee.search no data",
                extra={
                    "event": "cognee.search.no_data",
                    "operation": "recall_weaknesses",
                    "dataset": dataset,
                    "user_id": user_id,
                    "elapsed_ms": elapsed_ms(t0),
                },
            )
            return []
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
    # Anchored with the trailing newline (records always start "User: <id>\n") so one
    # user's id can't match as a prefix of another user's longer id.
    owned = [{"text": t} for r in results if f"{user_marker}\n" in (t := result_text(r))]
    # Drop mastered patterns so the opponent stops targeting what the user has beaten.
    items = filter_out_patterns(owned, exclude_patterns)[:10]
    logger.info(
        "cognee.search ok",
        extra={
            "event": "cognee.search.ok",
            "operation": "recall_weaknesses",
            "dataset": dataset,
            "user_id": user_id,
            "query_type": "CHUNKS",
            "results_raw": len(results),
            "results_owned": len(owned),
            "results_filtered": len(items),
            "excluded_patterns": sorted(exclude_patterns) if exclude_patterns else [],
            "elapsed_ms": elapsed_ms(t0),
        },
    )
    # Recalled user content is only surfaced at debug level, never info+.
    logger.debug(
        "cognee.search ok preview",
        extra={
            "event": "cognee.search.ok.preview",
            "operation": "recall_weaknesses",
            "user_id": user_id,
            "results_preview": [preview(it["text"], 120) for it in items[:3]],
        },
    )
    return items


async def recall_topic_weaknesses(
    user_id: str, topic: str, exclude_patterns: set[str] | None = None
) -> list[dict]:
    """Semantic search scoped to a specific debate topic.

    Finds session-summary and argument records where the user struggled on
    this exact topic — gives the voice/chat opponent topic-aware context from
    the very first turn instead of relying only on generic weakness patterns.
    """
    dataset = fingerprint_dataset(user_id)
    query = f"topic {topic} weak poor outcome lost needs improvement"
    user_marker = f"User: {user_id}"

    logger.info(
        "cognee.search start",
        extra={
            "event": "cognee.search.start",
            "operation": "recall_topic_weaknesses",
            "dataset": dataset,
            "user_id": user_id,
            "topic": topic,
            "query_type": "CHUNKS",
            "query": query,
            "top_k": 15,
        },
    )
    t0 = time.monotonic()
    try:
        results = await asyncio.wait_for(
            cognee.search(
                query_text=query,
                query_type=SearchType.CHUNKS,
                datasets=[dataset],
                top_k=15,
            ),
            timeout=SEARCH_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "cognee.search timeout",
            extra={
                "event": "cognee.search.timeout",
                "operation": "recall_topic_weaknesses",
                "dataset": dataset,
                "user_id": user_id,
                "topic": topic,
                "elapsed_ms": elapsed_ms(t0),
            },
        )
        return []
    except Exception as e:
        if type(e).__name__ == "NoDataError":
            return []
        logger.exception(
            "cognee.search error",
            extra={
                "event": "cognee.search.error",
                "operation": "recall_topic_weaknesses",
                "dataset": dataset,
                "user_id": user_id,
                "topic": topic,
                "elapsed_ms": elapsed_ms(t0),
            },
        )
        return []

    owned = [{"text": t} for r in results if f"{user_marker}\n" in (t := result_text(r))]
    items = filter_out_patterns(owned, exclude_patterns)[:5]
    logger.info(
        "cognee.search ok",
        extra={
            "event": "cognee.search.ok",
            "operation": "recall_topic_weaknesses",
            "dataset": dataset,
            "user_id": user_id,
            "topic": topic,
            "results_raw": len(results),
            "results_owned": len(owned),
            "results_filtered": len(items),
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
    await asyncio.wait_for(
        cognee.cognify(datasets=dataset, ontology_file_path=ontology_file()),
        timeout=COGNIFY_TIMEOUT,
    )
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
    await asyncio.wait_for(
        cognee.cognify(datasets=dataset, ontology_file_path=ontology_file()),
        timeout=COGNIFY_TIMEOUT,
    )
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
    await asyncio.wait_for(
        cognee.cognify(datasets=dataset, ontology_file_path=ontology_file()),
        timeout=COGNIFY_TIMEOUT,
    )
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
