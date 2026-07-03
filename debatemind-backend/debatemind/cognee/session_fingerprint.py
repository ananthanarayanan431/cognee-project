"""Session-scoped Cognitive Fingerprint, merging Cognee's Neo4j ArgumentRecord
nodes for this session with any Postgres exchanges Neo4j hasn't synced yet.

GET /api/sessions/{id}/graph and the per-turn SSE "graph" event
(routers/sessions.py) both call session_scoped_fingerprint() instead of the
Postgres-only debatemind/services/graph_svc.py::build_graph(). Unlike
build_graph (which aggregates every session sharing a topic), this is scoped
strictly to one session_id: only patterns from *this* debate.

The Neo4j write (debatemind/cognee/fingerprint.py::remember_argument(), fired
async via Celery from agents/pipeline.py::_remember_node) can lag behind the
Postgres Exchange row it's derived from -- most visibly right after the
current turn is saved, before the SSE "graph" event is built. To stay fresh,
_neo4j_tallies() counts how many of this session's ArgumentRecord nodes
Neo4j already has, and _merge_pending_exchanges() folds in whatever tail of
Postgres exchanges (ordered by created_at) falls past that count. If Neo4j is
unreachable entirely, the count is 0 and every exchange is reconstructed from
Postgres -- a graceful degrade to build_graph's old behavior for this session.
"""

from __future__ import annotations

from debatemind.agents.constants import PATTERN_TYPES

_VALID_PATTERNS = set(PATTERN_TYPES)


def _merge_pending_exchanges(
    tallies: dict[str, list[int]],
    neo4j_count: int,
    rows: list[tuple[str | None, str | None]],
) -> dict[str, list[int]]:
    """Fold Postgres (detected_pattern, outcome) rows past neo4j_count into
    tallies (pattern -> [count, wins]), mutating and returning it. rows must
    be ordered oldest-first so the tail (rows[neo4j_count:]) is exactly the
    exchanges Neo4j hasn't synced yet."""
    for detected_pattern, outcome in rows[neo4j_count:]:
        if detected_pattern not in _VALID_PATTERNS:
            continue
        tally = tallies.setdefault(detected_pattern, [0, 0])
        tally[0] += 1
        if outcome == "Won":
            tally[1] += 1
    return tallies
