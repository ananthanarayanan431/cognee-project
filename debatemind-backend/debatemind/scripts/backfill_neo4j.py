"""One-time backfill: materialize typed Cognee nodes for debates recorded in
Postgres *before* the worker's per-task engine fix (commit fbfe166) landed.

Until that fix, remember_argument()'s add_data_points() write silently failed on
a cross-event-loop asyncpg error ("another operation is in progress" / "attached
to a different loop"), so those sessions left cognify prose (DocumentChunks) in
Neo4j but no typed ArgumentRecord/Topic/UserProfile nodes. As a result /me/brain
(brain_view.py) and the knowledge-graph explorer read empty for that history.

This reads each pattern-tagged Exchange straight from Postgres and writes the
ArgumentRecord (+ its Topic and UserProfile) that remember_argument() would
have. It deliberately SKIPS the cognee.add()+cognify() prose/LLM pass — that
content already exists in Neo4j from the original sessions, and re-running it
would be slow and costly. Node ids are deterministic (schema.deterministic_id),
so the backfill is idempotent: re-running updates the same nodes in place rather
than duplicating them.

Run once against a configured (Neo4j) environment:

    python -m debatemind.scripts.backfill_neo4j            # all users
    python -m debatemind.scripts.backfill_neo4j --user <user_id>
"""

from __future__ import annotations

import logging
from typing import Any

from debatemind.cognee.fingerprint import _argument_summary
from debatemind.cognee.schema import (
    ArgumentRecord,
    Topic,
    UserProfile,
    deterministic_id,
    topic_id,
    user_profile_id,
)

logger = logging.getLogger(__name__)

_WRITE_BATCH = 50


def _evidence_label(score: float | None) -> str:
    """Coarse evidence-quality label from a stored judge_evidence score (0-10).

    ArgumentRecord.evidence_quality is a required string in the live write path
    ("Strong"/"Moderate"/"Weak"-style); Postgres only kept the numeric judge
    score, so map it back to a comparable label. Defaults to "Moderate" when the
    exchange was never scored."""
    if score is None:
        return "Moderate"
    if score >= 7:
        return "Strong"
    if score >= 4:
        return "Moderate"
    return "Weak"


def _build_typed_nodes(rows: list[dict[str, Any]]) -> list[Any]:
    """Turn Postgres exchange rows into the typed DataPoint nodes to write.

    Pure: constructs UserProfile/Topic/ArgumentRecord objects but performs no
    I/O, so the mapping is unit-testable. UserProfile and Topic are deduped per
    (user, topic) and carry deterministic ids; each ArgumentRecord's id is
    derived from (session_id, exchange_id) so a re-run is idempotent."""
    owners: dict[str, Any] = {}
    topics: dict[tuple[str, str], Any] = {}
    records: list[Any] = []

    for row in rows:
        uid = row["user_id"]
        topic = row["topic"]
        pattern = row["pattern_type"]
        if not uid or not topic or not pattern:
            continue

        owner = owners.get(uid)
        if owner is None:
            owner = UserProfile(id=user_profile_id(uid), user_id=uid)
            owners[uid] = owner

        tkey = (uid, topic.strip().lower())
        topic_node = topics.get(tkey)
        if topic_node is None:
            topic_node = Topic(id=topic_id(uid, topic), user_id=uid, name=topic)
            topics[tkey] = topic_node

        outcome = row.get("outcome") or "Neutral"
        evidence_quality = _evidence_label(row.get("evidence_score"))
        summary = _argument_summary(
            topic, pattern, row.get("fallacy"), evidence_quality, outcome, ""
        )
        records.append(
            ArgumentRecord(
                id=deterministic_id("ArgumentRecord", row["session_id"], row["exchange_id"]),
                user_id=uid,
                session_id=row["session_id"],
                topic_name=topic,
                claim_text=row.get("claim_text") or "",
                pattern_type=pattern,
                fallacy=row.get("fallacy"),
                evidence_quality=evidence_quality,
                outcome=outcome,
                reasoning="",
                summary=summary,
                topic=topic_node,
                owner=owner,
            )
        )

    # Owners and topics first so the ArgumentRecords' typed edges resolve.
    return list(owners.values()) + list(topics.values()) + records


async def _load_rows(user_id: str | None) -> list[dict[str, Any]]:
    from sqlalchemy import select

    from debatemind.database import AsyncSessionLocal
    from debatemind.models.session import DebateSession, Exchange

    stmt = (
        select(
            DebateSession.user_id,
            Exchange.session_id,
            DebateSession.topic,
            Exchange.id.label("exchange_id"),
            Exchange.user_message,
            Exchange.detected_pattern,
            Exchange.fallacy,
            Exchange.judge_evidence,
            Exchange.outcome,
        )
        .join(DebateSession, Exchange.session_id == DebateSession.id)
        .where(Exchange.detected_pattern.isnot(None))
        .order_by(Exchange.created_at)
    )
    if user_id:
        stmt = stmt.where(DebateSession.user_id == user_id)

    async with AsyncSessionLocal() as db:
        result = await db.execute(stmt)
        return [
            {
                "user_id": r.user_id,
                "session_id": r.session_id,
                "topic": r.topic,
                "exchange_id": r.exchange_id,
                "claim_text": r.user_message,
                "pattern_type": r.detected_pattern,
                "fallacy": r.fallacy,
                "evidence_score": r.judge_evidence,
                "outcome": r.outcome,
            }
            for r in result.all()
        ]


async def backfill(user_id: str | None = None) -> dict[str, int]:
    """Read pattern-tagged exchanges from Postgres and write their typed nodes to
    the configured Cognee graph. Returns counts. Assumes cognee is already
    configured and set up on the current event loop."""
    from cognee.tasks.storage import add_data_points

    rows = await _load_rows(user_id)
    nodes = _build_typed_nodes(rows)
    if not nodes:
        logger.info("backfill: nothing to write (user_id=%s)", user_id)
        return {"exchanges": 0, "users": 0, "topics": 0, "arguments": 0}

    for i in range(0, len(nodes), _WRITE_BATCH):
        await add_data_points(nodes[i : i + _WRITE_BATCH])

    stats = {
        "exchanges": len(rows),
        "users": sum(1 for n in nodes if isinstance(n, UserProfile)),
        "topics": sum(1 for n in nodes if isinstance(n, Topic)),
        "arguments": sum(1 for n in nodes if isinstance(n, ArgumentRecord)),
    }
    logger.info("backfill complete: %s", stats)
    return stats


def main() -> None:
    import argparse
    import asyncio

    from debatemind.config import settings
    from debatemind.services.cognee_config import configure_cognee

    parser = argparse.ArgumentParser(description="Backfill typed Cognee nodes from Postgres.")
    parser.add_argument("--user", default=None, help="Only backfill this user_id (default: all).")
    args = parser.parse_args()

    configure_cognee(settings)

    async def _run() -> dict[str, int]:
        from cognee.modules.engine.operations.setup import setup as cognee_setup

        await cognee_setup()
        return await backfill(args.user)

    stats = asyncio.run(_run())
    print(f"Backfill complete: {stats}")


if __name__ == "__main__":
    main()
