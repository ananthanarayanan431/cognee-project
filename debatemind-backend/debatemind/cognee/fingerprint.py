"""User fingerprint operations.

Tracks each user's argumentation patterns, fallacies, and mastery state in the
cognee knowledge graph so the opponent and progress views can adapt over time.

Operations:
  remember_argument        — write a new argument record into the fingerprint
  remember_session_summary — write a session-level performance summary
  improve_fingerprint      — re-index the fingerprint after a batch of writes
"""

import asyncio
import logging
import time

import cognee
from cognee.tasks.storage import add_data_points

from debatemind.cognee._base import (
    ADD_TIMEOUT,
    COGNIFY_TIMEOUT,
    elapsed_ms,
    fingerprint_dataset,
    ontology_file,
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
    reasoning_approach: str | None = None,
    cognitive_bias: str | None = None,
) -> str:
    """A natural-language sentence describing the argument.

    The terse `key: value` markers alone give cognify's LLM extractor little to
    work with; a prose sentence that names the topic, pattern, evidence, and
    fallacy lets it link the argument to a KnowledgeDomain and type it against
    the ontology (ReasoningApproach / EvidenceType / Fallacy). Naming the
    reasoning approach and cognitive bias explicitly (when the extractor found
    them) is what lets cognify create the corresponding ontology entity nodes —
    the read-side bridge in recall.py then attributes them back to this user.
    The reasoning sentence, when present, is the richest signal for those types.
    """
    fallacy_clause = f" and committed the {fallacy} fallacy" if fallacy else ""
    approach_clause = f" using {reasoning_approach} reasoning" if reasoning_approach else ""
    bias_clause = f", exhibiting {cognitive_bias}" if cognitive_bias else ""
    summary = (
        f'In a debate about "{topic}", the user made a {pattern_type} argument'
        f"{approach_clause} with {evidence_quality} evidence{fallacy_clause}{bias_clause}; "
        f"the outcome was {outcome}."
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
    reasoning_approach: str | None = None,
    cognitive_bias: str | None = None,
) -> None:
    text = (
        f"User: {user_id}\n"
        f"Session: {session_id}\n"
        f"Topic: {topic}\n"
        f"Claim: {claim_text}\n"
        f"ArgumentPattern: {pattern_type}\n"
        f"Fallacy: {fallacy or 'None'}\n"
        f"ReasoningApproach: {reasoning_approach or 'None'}\n"
        f"CognitiveBias: {cognitive_bias or 'None'}\n"
        f"Evidence: {evidence_quality}\n"
        f"Outcome: {outcome}\n"
    )
    if reasoning:
        text += f"Reasoning: {reasoning}\n"
    summary = _argument_summary(
        topic,
        pattern_type,
        fallacy,
        evidence_quality,
        outcome,
        reasoning,
        reasoning_approach,
        cognitive_bias,
    )
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
            reasoning_approach=reasoning_approach,
            cognitive_bias=cognitive_bias,
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
