"""Forget — real deletion: remove a Cognee graph node and its vector embedding
so it can never resurface through recall.py again.

Mastering a debate pattern (or a user asking to forget a personal fact)
deletes the matching typed node(s) from BOTH stores — the graph node
(get_graph_engine().delete_nodes) and its vector embedding
(get_vector_engine().delete_data_points) — rather than writing a soft-delete
marker that a downstream filter has to remember to apply. Mirrors
ContextFirewall's forget.py governance model.
"""

from __future__ import annotations

import logging

from debatemind.cognee.recall import owned_nodes

logger = logging.getLogger(__name__)


async def _delete_nodes(node_ids: list[str], *, collection: str) -> None:
    if not node_ids:
        return
    from cognee.infrastructure.databases.graph import get_graph_engine
    from cognee.infrastructure.databases.vector import get_vector_engine

    graph_engine = await get_graph_engine()
    await graph_engine.delete_nodes(node_ids)

    vector_engine = get_vector_engine()  # sync factory -> handle
    try:
        await vector_engine.delete_data_points(collection, node_ids)
    except Exception:
        logger.exception(
            "vector delete_data_points failed for collection %s ids=%s — graph node(s) "
            "already deleted; a stale embedding may still rank in future searches",
            collection,
            node_ids,
        )


async def forget_pattern(user_id: str, pattern_type: str) -> None:
    """Permanently delete every ArgumentRecord this user has for `pattern_type`.

    Called when a pattern is mastered (debatemind/agents/pipeline.py's
    `_mastery_prune_node`). Postgres' MasteryLog is the source of truth for
    gating the opponent (see mastery_svc.get_active_mastered_patterns); this
    delete makes the underlying evidence actually disappear from recall.py and
    the knowledge-graph view too, rather than merely being hidden. This is a
    one-way action: reactivating the pattern later does not restore the
    deleted evidence, only resumes future targeting.
    """
    owned = await owned_nodes("ArgumentRecord", user_id)
    node_ids = [nid for nid, props in owned.items() if props.get("pattern_type") == pattern_type]
    if not node_ids:
        logger.info(
            "forget_pattern found nothing to delete",
            extra={"user_id": user_id, "pattern_type": pattern_type},
        )
        return
    await _delete_nodes(node_ids, collection="ArgumentRecord_summary")
    logger.info(
        "forget_pattern deleted nodes",
        extra={"user_id": user_id, "pattern_type": pattern_type, "deleted": len(node_ids)},
    )


async def forget_personal_fact(user_id: str, node_id: str) -> dict:
    """Permanently delete one PersonalFact node this user owns.

    Returns a status dict rather than raising, so the router can surface a
    clean 404-shaped response instead of a 500 when the fact doesn't exist or
    belongs to someone else.
    """
    owned = await owned_nodes("PersonalFact", user_id)
    if node_id not in owned:
        return {"node_id": node_id, "status": "not_found"}
    await _delete_nodes([node_id], collection="PersonalFact_fact_text")
    logger.info("forget_personal_fact deleted node", extra={"user_id": user_id, "node_id": node_id})
    return {"node_id": node_id, "status": "forgotten"}
