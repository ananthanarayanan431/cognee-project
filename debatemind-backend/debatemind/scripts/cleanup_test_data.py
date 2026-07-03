"""Purge diagnostic/test artifacts from every Cognee store (graph, vector, relational).

Debug sessions and smoke tests wrote fingerprint data under synthetic user ids
(diag-e2e-*, smoketest_*, writecheck_*, test-isolation-*). Ownership filtering in
recall.py keeps them out of real users' prompts, but they still pollute the
global graph and the shared per-class vector collections that rank recall
results, and they show up in whole-graph views. A "test user" is any fingerprint
dataset whose embedded user id has no row in the app's `users` table — so the
script needs no hardcoded id list and is safe to re-run any time.

For each test user this removes:
  Neo4j     — typed nodes (UserProfile/Topic/ArgumentRecord/PersonalFact/
              SessionSummary) owned via `user_id`, prose nodes (DocumentChunk/
              TextDocument/TextSummary) carrying the `User: {id}` marker, then
              any Entity/EntityType left orphaned (no path to a surviving chunk).
  pgvector  — rows in every per-class collection whose id matched a deleted node.
  relational— the `datasets` row (dataset_data cascades) and orphaned `data` rows.

Usage:

    python -m debatemind.scripts.cleanup_test_data --dry-run   # report only
    python -m debatemind.scripts.cleanup_test_data             # delete
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import re

from sqlalchemy import text

logger = logging.getLogger(__name__)

_DATASET_RE = re.compile(r"^user_(?P<uid>.+)_fingerprint$")

# Per-class vector collections (pgvector tables in the cognee DB). A class
# missing here only leaves harmless unranked rows behind — recall filters by
# graph ownership, never by vector rows alone.
_VECTOR_COLLECTIONS = (
    "ArgumentRecord_summary",
    "DocumentChunk_text",
    "EdgeType_relationship_name",
    "EntityType_name",
    "Entity_name",
    "PersonalFact_fact_text",
    "SessionSummary_summary",
    "TextDocument_name",
    "TextSummary_text",
    "Topic_name",
)


async def _real_user_ids() -> set[str]:
    from sqlalchemy import select

    from debatemind.database import AsyncSessionLocal
    from debatemind.models.user import User

    async with AsyncSessionLocal() as db:
        rows = await db.execute(select(User.id))
        return {str(r[0]) for r in rows}


async def _test_datasets() -> list[tuple[str, str, str]]:
    """(dataset_id, dataset_name, embedded_user_id) for non-real users."""
    from cognee.infrastructure.databases.relational import get_relational_engine

    real = await _real_user_ids()
    engine = get_relational_engine()
    async with engine.get_async_session() as session:
        rows = (await session.execute(text("SELECT id, name FROM datasets"))).all()
    out = []
    for ds_id, name in rows:
        m = _DATASET_RE.match(name or "")
        if m and m.group("uid") not in real:
            out.append((str(ds_id), name, m.group("uid")))
    return out


async def _graph_cleanup(test_uids: list[str], dry_run: bool) -> list[str]:
    """Delete test-owned graph nodes; return the deleted node ids (uuid strings)."""
    from cognee.infrastructure.databases.graph import get_graph_engine

    engine = await get_graph_engine()
    markers = [f"User: {uid}" for uid in test_uids]

    typed = await engine.query(
        "MATCH (n) WHERE n.user_id IN $uids RETURN n.id AS id", {"uids": test_uids}
    )
    prose = await engine.query(
        """
        MATCH (c:DocumentChunk) WHERE any(m IN $markers WHERE c.text CONTAINS m)
        OPTIONAL MATCH (c)-[:is_part_of]->(d:TextDocument)
        OPTIONAL MATCH (s:TextSummary)-[:made_from]->(c)
        RETURN collect(DISTINCT c.id) + collect(DISTINCT d.id) + collect(DISTINCT s.id) AS ids
        """,
        {"markers": markers},
    )
    doomed = {str(r["id"]) for r in typed if r.get("id")}
    for row in prose:
        doomed.update(str(i) for i in (row.get("ids") or []) if i)

    if dry_run:
        logger.info("[dry-run] would delete %d owned/prose graph nodes", len(doomed))
        return sorted(doomed)

    if doomed:
        await engine.query("MATCH (n) WHERE n.id IN $ids DETACH DELETE n", {"ids": sorted(doomed)})

    # Entities/EntityTypes only reachable from deleted test prose are now
    # stranded: no surviving DocumentChunk within 3 hops means no recall path
    # (recall.py walks out from chunks) and no real-owned anchor.
    orphan_entities = await engine.query(
        """
        MATCH (e:Entity)
        WHERE NOT EXISTS { MATCH (e)-[*1..3]-(:DocumentChunk) }
        WITH e, e.id AS id DETACH DELETE e RETURN id
        """,
        {},
    )
    orphan_types = await engine.query(
        """
        MATCH (t:EntityType)
        WHERE NOT ()-[:is_a]->(t)
        WITH t, t.id AS id DETACH DELETE t RETURN id
        """,
        {},
    )
    doomed.update(str(r["id"]) for r in orphan_entities if r.get("id"))
    doomed.update(str(r["id"]) for r in orphan_types if r.get("id"))
    logger.info(
        "graph: deleted %d nodes (%d orphaned entities/types)",
        len(doomed),
        len(orphan_entities) + len(orphan_types),
    )
    return sorted(doomed)


async def _vector_cleanup(node_ids: list[str], dry_run: bool) -> int:
    from cognee.infrastructure.databases.relational import get_relational_engine

    if not node_ids:
        return 0
    engine = get_relational_engine()
    deleted = 0
    async with engine.get_async_session() as session:
        for table in _VECTOR_COLLECTIONS:
            exists = await session.execute(
                text("SELECT to_regclass(:t)"), {"t": f'public."{table}"'}
            )
            if exists.scalar() is None:
                continue
            if dry_run:
                res = await session.execute(
                    text(f'SELECT count(*) FROM "{table}" WHERE id::text = ANY(:ids)'),
                    {"ids": node_ids},
                )
                deleted += res.scalar() or 0
            else:
                res = await session.execute(
                    text(f'DELETE FROM "{table}" WHERE id::text = ANY(:ids)'),
                    {"ids": node_ids},
                )
                deleted += res.rowcount or 0
        if not dry_run:
            await session.commit()
    logger.info("%svector: %d rows", "[dry-run] " if dry_run else "", deleted)
    return deleted


async def _relational_cleanup(dataset_ids: list[str], dry_run: bool) -> None:
    from cognee.infrastructure.databases.relational import get_relational_engine

    if not dataset_ids:
        return
    engine = get_relational_engine()
    async with engine.get_async_session() as session:
        if dry_run:
            logger.info("[dry-run] would delete %d dataset rows", len(dataset_ids))
            return
        await session.execute(
            text("DELETE FROM datasets WHERE id::text = ANY(:ids)"), {"ids": dataset_ids}
        )
        # data rows are shared across datasets via dataset_data; drop the ones
        # no surviving dataset references (acls cascade with them).
        res = await session.execute(
            text("DELETE FROM data WHERE id NOT IN (SELECT data_id FROM dataset_data)")
        )
        await session.commit()
        logger.info(
            "relational: %d datasets, %d orphaned data rows", len(dataset_ids), res.rowcount
        )


async def cleanup(dry_run: bool = False) -> None:
    datasets = await _test_datasets()
    if not datasets:
        logger.info("no test datasets found — stores are clean")
        return
    for _, name, uid in datasets:
        logger.info("test dataset: %s (user %s)", name, uid)

    node_ids = await _graph_cleanup([uid for _, _, uid in datasets], dry_run)
    await _vector_cleanup(node_ids, dry_run)
    await _relational_cleanup([ds_id for ds_id, _, _ in datasets], dry_run)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report what would be deleted")
    args = parser.parse_args()

    from debatemind.config import settings
    from debatemind.services.cognee_config import configure_cognee

    configure_cognee(settings)
    asyncio.run(cleanup(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
