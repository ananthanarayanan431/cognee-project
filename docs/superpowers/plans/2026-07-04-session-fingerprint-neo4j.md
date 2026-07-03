# Session-scoped Cognitive Fingerprint (Neo4j-backed) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the in-session "Cognitive Fingerprint" panel read from Cognee's Neo4j `ArgumentRecord` nodes (scoped strictly to the current session_id) instead of the cross-session Postgres query it uses today, while staying fresh when the async Neo4j write hasn't caught up yet.

**Architecture:** A new pure-ish module, `debatemind/cognee/session_fingerprint.py`, exposes `session_scoped_fingerprint(user_id, session_id, topic) -> GraphOut`. It reads Neo4j `ArgumentRecord` nodes filtered to this exact `session_id`, counts how many it found, then pulls this session's Postgres `Exchange` rows and folds in only the tail past that count (the exchanges Neo4j hasn't synced yet, or — if Neo4j is unreachable — every exchange). `routers/sessions.py` swaps its two `build_graph(...)` call sites (the per-turn SSE stream and the `GET /{id}/graph` endpoint) to call this new function instead.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async ORM (SQLite in-memory for tests), Cognee's Neo4j graph engine (`cognee.infrastructure.databases.graph.get_graph_engine`), pytest + pytest-asyncio.

## Global Constraints

- Response shape must stay exactly `GraphOut(nodes: list[GraphNode], edges: list[GraphEdge])` from `debatemind/schemas/graph.py` — the frontend (`FingerprintGraph.tsx`) is not being changed.
- Only patterns whose `pattern_type`/`detected_pattern` is in `debatemind.agents.constants.PATTERN_TYPES` count (mirrors `graph_svc.build_graph`'s `_VALID_PATTERNS` filter).
- Node/edge construction must match `graph_svc.build_graph`'s existing formula exactly: root `GraphNode(id="topic", label=topic[:20], type="topic", weight=1.0)`, then `Counter.most_common(8)` patterns, `weight = round(min(count/total*3, 0.95), 2)`, `type = "strength"` if `win_rate >= 0.5` else `"weakness"`, one `GraphEdge(source="topic", target=pattern, weight=weight)` per pattern.
- Scoping is strictly by `session_id` (not by topic-across-sessions) — this is a confirmed, intentional behavior change from today's `graph_svc.build_graph`.
- `debatemind/services/graph_svc.py::build_graph` is NOT deleted or modified — it stays for `GET /api/users/me/fingerprint`, which is out of scope.
- Spec: `docs/superpowers/specs/2026-07-04-session-fingerprint-neo4j-design.md`.

---

### Task 1: `session_scoped_fingerprint` module and its unit tests

**Files:**
- Create: `debatemind-backend/debatemind/cognee/session_fingerprint.py`
- Create: `debatemind-backend/tests/test_cognee_session_fingerprint.py`

**Interfaces:**
- Consumes: `debatemind.cognee.graph_view._node_props(entry) -> tuple[str, dict]` (existing), `debatemind.agents.constants.PATTERN_TYPES` (existing list[str]), `debatemind.database.AsyncSessionLocal` (existing `async_sessionmaker`), `debatemind.models.session.Exchange` (existing ORM model with `session_id`, `detected_pattern`, `outcome`, `created_at` columns), `debatemind.schemas.graph.{GraphNode, GraphEdge, GraphOut}` (existing pydantic models), `cognee.infrastructure.databases.graph.get_graph_engine()` (existing async function returning an engine with `async def get_graph_data() -> tuple[list, list]`).
- Produces: `session_scoped_fingerprint(user_id: str, session_id: str, topic: str) -> GraphOut` — consumed by Task 2. Also produces two internal helpers importable by tests: `_merge_pending_exchanges(tallies: dict[str, list[int]], neo4j_count: int, rows: list[tuple[str | None, str | None]]) -> dict[str, list[int]]` and `_neo4j_tallies(user_id: str, session_id: str) -> tuple[dict[str, list[int]], int]`.

- [ ] **Step 1: Write failing tests for `_merge_pending_exchanges`**

Create `debatemind-backend/tests/test_cognee_session_fingerprint.py`:

```python
"""
Unit tests for debatemind.cognee.session_fingerprint.session_scoped_fingerprint
-- the session_id-scoped Cognitive Fingerprint. Unlike graph_svc.build_graph
(which aggregates every session sharing a topic), this is scoped strictly to
one session_id and merges in Postgres exchanges the async Neo4j write hasn't
caught up to yet. get_graph_engine() is mocked; Postgres is a real in-memory
SQLite.
"""

from debatemind.cognee import session_fingerprint


def test_merge_only_applies_to_the_tail_past_neo4j_count():
    tallies = {"StrawMan": [2, 2]}  # Neo4j already has 2 synced StrawMan wins
    rows = [
        ("StrawMan", "Won"),
        ("StrawMan", "Won"),
        ("EvidenceBased", "Lost"),
    ]
    result = session_fingerprint._merge_pending_exchanges(tallies, neo4j_count=2, rows=rows)
    assert result == {"StrawMan": [2, 2], "EvidenceBased": [1, 0]}


def test_merge_reconstructs_everything_when_neo4j_count_is_zero():
    tallies: dict = {}
    rows = [("StrawMan", "Lost"), ("StrawMan", "Won")]
    result = session_fingerprint._merge_pending_exchanges(tallies, neo4j_count=0, rows=rows)
    assert result == {"StrawMan": [2, 1]}


def test_merge_ignores_patterns_outside_pattern_types():
    result = session_fingerprint._merge_pending_exchanges({}, neo4j_count=0, rows=[("NotReal", "Won")])
    assert result == {}


def test_merge_is_a_no_op_when_neo4j_already_has_every_exchange():
    tallies = {"StrawMan": [3, 1]}
    rows = [("StrawMan", "Lost"), ("StrawMan", "Lost"), ("StrawMan", "Won")]
    result = session_fingerprint._merge_pending_exchanges(tallies, neo4j_count=3, rows=rows)
    assert result == {"StrawMan": [3, 1]}
```

- [ ] **Step 2: Run the tests and confirm they fail on import**

Run: `cd debatemind-backend && .venv/bin/pytest tests/test_cognee_session_fingerprint.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'debatemind.cognee.session_fingerprint'`

- [ ] **Step 3: Implement the module skeleton and `_merge_pending_exchanges`**

Create `debatemind-backend/debatemind/cognee/session_fingerprint.py`:

```python
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

import logging
from collections import Counter, defaultdict

from sqlalchemy import select

from debatemind.agents.constants import PATTERN_TYPES
from debatemind.cognee.graph_view import _node_props
from debatemind.database import AsyncSessionLocal
from debatemind.models.session import Exchange
from debatemind.schemas.graph import GraphEdge, GraphNode, GraphOut

logger = logging.getLogger(__name__)

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
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `cd debatemind-backend && .venv/bin/pytest tests/test_cognee_session_fingerprint.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add debatemind-backend/debatemind/cognee/session_fingerprint.py debatemind-backend/tests/test_cognee_session_fingerprint.py
git commit -m "feat: add pending-exchange merge for session-scoped fingerprint"
```

- [ ] **Step 6: Write failing tests for `_neo4j_tallies`**

Add `from unittest.mock import AsyncMock, patch` to the top of
`debatemind-backend/tests/test_cognee_session_fingerprint.py`, above the
existing `from debatemind.cognee import session_fingerprint` line (keep
imports at the top of the file so ruff's import-order check stays clean at
every commit). Then append the rest below the existing tests:

```python
class _FakeGraphEngine:
    def __init__(self, nodes):
        self._nodes = nodes

    async def get_graph_data(self):
        return self._nodes, []


def _patched(nodes):
    return patch(
        "cognee.infrastructure.databases.graph.get_graph_engine",
        new=AsyncMock(return_value=_FakeGraphEngine(nodes)),
    )


def _record(nid, user_id, session_id, pattern, outcome):
    return (
        nid,
        {
            "id": nid,
            "type": "ArgumentRecord",
            "user_id": user_id,
            "session_id": session_id,
            "pattern_type": pattern,
            "outcome": outcome,
        },
    )


async def test_neo4j_tallies_counts_matching_records():
    nodes = [
        _record("a", "u1", "s1", "StrawMan", "Lost"),
        _record("b", "u1", "s1", "StrawMan", "Won"),
    ]
    with _patched(nodes):
        tallies, count = await session_fingerprint._neo4j_tallies("u1", "s1")

    assert tallies == {"StrawMan": [2, 1]}
    assert count == 2


async def test_neo4j_tallies_excludes_other_sessions_and_users():
    nodes = [
        _record("a", "u1", "s1", "StrawMan", "Won"),
        _record("b", "u1", "s2", "AdHominem", "Won"),  # other session
        _record("c", "u2", "s1", "Concession", "Won"),  # other user
    ]
    with _patched(nodes):
        tallies, count = await session_fingerprint._neo4j_tallies("u1", "s1")

    assert tallies == {"StrawMan": [1, 1]}
    assert count == 1


async def test_neo4j_tallies_ignores_non_argument_record_nodes():
    nodes = [("e", {"id": "e", "type": "Entity", "name": "StrawMan"})]
    with _patched(nodes):
        tallies, count = await session_fingerprint._neo4j_tallies("u1", "s1")

    assert tallies == {}
    assert count == 0


async def test_neo4j_tallies_returns_empty_on_engine_failure():
    with patch(
        "cognee.infrastructure.databases.graph.get_graph_engine",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        tallies, count = await session_fingerprint._neo4j_tallies("u1", "s1")

    assert tallies == {}
    assert count == 0
```

- [ ] **Step 7: Run the tests and confirm they fail**

Run: `cd debatemind-backend && .venv/bin/pytest tests/test_cognee_session_fingerprint.py -v`
Expected: FAIL — `AttributeError: module 'debatemind.cognee.session_fingerprint' has no attribute '_neo4j_tallies'`

- [ ] **Step 8: Implement `_neo4j_tallies`**

Append to `debatemind-backend/debatemind/cognee/session_fingerprint.py`:

```python
async def _neo4j_tallies(user_id: str, session_id: str) -> tuple[dict[str, list[int]], int]:
    """(pattern -> [count, wins], number of this session's ArgumentRecord
    nodes found) from Cognee's Neo4j graph. Returns ({}, 0) if the graph
    engine is unavailable."""
    from cognee.infrastructure.databases.graph import get_graph_engine

    try:
        engine = await get_graph_engine()
        raw_nodes, _raw_edges = await engine.get_graph_data()
    except Exception:
        logger.exception("get_graph_data failed for session %s", session_id)
        return {}, 0

    tallies: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    neo4j_count = 0
    for entry in raw_nodes:
        _nid, props = _node_props(entry)
        if props.get("type") != "ArgumentRecord":
            continue
        if props.get("user_id") != user_id or props.get("session_id") != session_id:
            continue
        pattern = str(props.get("pattern_type") or "").strip()
        if not pattern:
            continue
        neo4j_count += 1
        tally = tallies[pattern]
        tally[0] += 1
        if props.get("outcome") == "Won":
            tally[1] += 1

    return dict(tallies), neo4j_count
```

- [ ] **Step 9: Run the tests and confirm they pass**

Run: `cd debatemind-backend && .venv/bin/pytest tests/test_cognee_session_fingerprint.py -v`
Expected: 8 passed

- [ ] **Step 10: Commit**

```bash
git add debatemind-backend/debatemind/cognee/session_fingerprint.py debatemind-backend/tests/test_cognee_session_fingerprint.py
git commit -m "feat: read session-scoped ArgumentRecord tallies from Neo4j"
```

- [ ] **Step 11: Write failing tests for `session_scoped_fingerprint`**

Add these to the top of `debatemind-backend/tests/test_cognee_session_fingerprint.py`,
alongside the existing imports (keep all imports at the top of the file):

```python
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from debatemind.database import Base
from debatemind.models.session import DebateSession, Exchange
```

Then append the rest below the existing tests:

```python
@pytest.fixture
async def seed(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(session_fingerprint, "AsyncSessionLocal", factory)

    async def _seed(session_id: str, user_id: str, topic: str, rows: list[tuple[str, str]]):
        """rows = [(detected_pattern, outcome), ...], oldest first."""
        async with factory() as db:
            db.add(DebateSession(id=session_id, user_id=user_id, topic=topic))
            await db.flush()
            for i, (pattern, outcome) in enumerate(rows):
                db.add(
                    Exchange(
                        session_id=session_id,
                        turn_number=i + 1,
                        user_message="msg",
                        detected_pattern=pattern,
                        outcome=outcome,
                    )
                )
            await db.commit()

    yield _seed
    await engine.dispose()


async def test_empty_session_returns_empty_graph(seed):
    await seed("s1", "u1", "UBI", [])
    with _patched([]):
        graph = await session_fingerprint.session_scoped_fingerprint("u1", "s1", "UBI")

    assert graph.nodes == []
    assert graph.edges == []


async def test_topic_node_is_first_and_label_truncated_to_20(seed):
    long_topic = "Should social media platforms be regulated by governments"
    await seed("s1", "u1", long_topic, [("StrawMan", "Lost")])
    with _patched([_record("a", "u1", "s1", "StrawMan", "Lost")]):
        graph = await session_fingerprint.session_scoped_fingerprint("u1", "s1", long_topic)

    assert graph.nodes[0].id == "topic"
    assert graph.nodes[0].type == "topic"
    assert graph.nodes[0].weight == 1.0
    assert graph.nodes[0].label == long_topic[:20]


async def test_fully_synced_session_uses_neo4j_tallies_without_duplication(seed):
    await seed("s1", "u1", "UBI", [("EvidenceBased", "Won")])
    with _patched([_record("a", "u1", "s1", "EvidenceBased", "Won")]):
        graph = await session_fingerprint.session_scoped_fingerprint("u1", "s1", "UBI")

    by_id = {n.id: n for n in graph.nodes}
    assert by_id["EvidenceBased"].type == "strength"
    assert by_id["EvidenceBased"].weight == 0.95  # 1/1 * 3 capped


async def test_merges_pending_exchange_neo4j_has_not_synced_yet(seed):
    # Neo4j only has the first exchange; the second hasn't synced yet.
    await seed("s1", "u1", "UBI", [("EvidenceBased", "Won"), ("StrawMan", "Lost")])
    with _patched([_record("a", "u1", "s1", "EvidenceBased", "Won")]):
        graph = await session_fingerprint.session_scoped_fingerprint("u1", "s1", "UBI")

    by_id = {n.id: n for n in graph.nodes}
    assert by_id["EvidenceBased"].type == "strength"
    assert by_id["StrawMan"].type == "weakness"


async def test_falls_back_to_postgres_when_neo4j_unavailable(seed):
    await seed("s1", "u1", "UBI", [("StrawMan", "Lost"), ("StrawMan", "Lost")])
    with patch(
        "cognee.infrastructure.databases.graph.get_graph_engine",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        graph = await session_fingerprint.session_scoped_fingerprint("u1", "s1", "UBI")

    by_id = {n.id: n for n in graph.nodes}
    assert by_id["StrawMan"].type == "weakness"


async def test_excludes_other_sessions_from_postgres_and_neo4j(seed):
    await seed("s1", "u1", "UBI", [("StrawMan", "Lost")])
    await seed("s2", "u1", "UBI", [("Concession", "Won")])  # different session, same topic
    with _patched([_record("a", "u1", "s1", "StrawMan", "Lost")]):
        graph = await session_fingerprint.session_scoped_fingerprint("u1", "s1", "UBI")

    ids = {n.id for n in graph.nodes if n.id != "topic"}
    assert ids == {"StrawMan"}


async def test_caps_pattern_nodes_at_eight(seed):
    rows = [(f"Pattern{i}", "Won") for i in range(10)]
    # Only the first 8 pattern names matter for this cap check; reuse valid
    # names by cycling through PATTERN_TYPES-adjacent stand-ins isn't needed --
    # patch _VALID_PATTERNS-independent path via Neo4j records directly.
    neo4j_nodes = [_record(f"n{i}", "u1", "s1", f"Pattern{i}", "Won") for i in range(10)]
    with _patched(neo4j_nodes):
        # Bypass the PATTERN_TYPES filter for this synthetic test by seeding
        # no Postgres rows at all -- neo4j_count will exceed len(rows) (0),
        # so _merge_pending_exchanges's rows[neo4j_count:] slice is empty and
        # every count comes straight from Neo4j regardless of _VALID_PATTERNS.
        await seed("s1", "u1", "UBI", [])
        graph = await session_fingerprint.session_scoped_fingerprint("u1", "s1", "UBI")

    pattern_nodes = [n for n in graph.nodes if n.id != "topic"]
    assert len(pattern_nodes) == 8
```

- [ ] **Step 12: Run the tests and confirm they fail**

Run: `cd debatemind-backend && .venv/bin/pytest tests/test_cognee_session_fingerprint.py -v`
Expected: FAIL — `AttributeError: module 'debatemind.cognee.session_fingerprint' has no attribute 'session_scoped_fingerprint'`

- [ ] **Step 13: Implement `session_scoped_fingerprint`**

Append to `debatemind-backend/debatemind/cognee/session_fingerprint.py`:

```python
async def session_scoped_fingerprint(user_id: str, session_id: str, topic: str) -> GraphOut:
    tallies, neo4j_count = await _neo4j_tallies(user_id, session_id)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Exchange.detected_pattern, Exchange.outcome)
            .where(Exchange.session_id == session_id)
            .where(Exchange.detected_pattern.is_not(None))
            .order_by(Exchange.created_at)
        )
        rows = result.fetchall()

    tallies = _merge_pending_exchanges(tallies, neo4j_count, list(rows))

    pattern_counts = Counter({pattern: count for pattern, (count, _wins) in tallies.items()})
    if not pattern_counts:
        return GraphOut(nodes=[], edges=[])

    total = sum(pattern_counts.values())
    nodes: list[GraphNode] = [GraphNode(id="topic", label=topic[:20], type="topic", weight=1.0)]
    edges: list[GraphEdge] = []

    for pattern, count in pattern_counts.most_common(8):
        weight = round(min(count / total * 3, 0.95), 2)
        win_rate = tallies[pattern][1] / count
        node_type = "strength" if win_rate >= 0.5 else "weakness"
        nodes.append(GraphNode(id=pattern, label=pattern, type=node_type, weight=weight))
        edges.append(GraphEdge(source="topic", target=pattern, weight=weight))

    return GraphOut(nodes=nodes, edges=edges)
```

- [ ] **Step 14: Run the tests and confirm they pass**

Run: `cd debatemind-backend && .venv/bin/pytest tests/test_cognee_session_fingerprint.py -v`
Expected: 15 passed

- [ ] **Step 15: Commit**

```bash
git add debatemind-backend/debatemind/cognee/session_fingerprint.py debatemind-backend/tests/test_cognee_session_fingerprint.py
git commit -m "feat: assemble session-scoped GraphOut from merged Neo4j+Postgres tallies"
```

---

### Task 2: Wire the router's two call sites to `session_scoped_fingerprint`

**Files:**
- Modify: `debatemind-backend/debatemind/routers/sessions.py:31` (import), `:308` (SSE stream), `:544` (GET endpoint)
- Modify: `debatemind-backend/tests/test_sessions_router.py`

**Interfaces:**
- Consumes: `session_scoped_fingerprint(user_id: str, session_id: str, topic: str) -> GraphOut` from Task 1.
- Produces: nothing new consumed by later tasks — this is the final task.

- [ ] **Step 1: Update the existing streaming test to target the new symbol**

In `debatemind-backend/tests/test_sessions_router.py`, change line 106 from:

```python
    monkeypatch.setattr(
        sessions_router, "build_graph", AsyncMock(return_value=GraphOut(nodes=[], edges=[]))
    )
```

to:

```python
    monkeypatch.setattr(
        sessions_router,
        "session_scoped_fingerprint",
        AsyncMock(return_value=GraphOut(nodes=[], edges=[])),
    )
```

- [ ] **Step 2: Add tests for the `GET /{session_id}/graph` endpoint**

Add to `debatemind-backend/tests/test_sessions_router.py` (add `GraphNode` to the existing `from debatemind.schemas.graph import GraphOut` import line so it reads `from debatemind.schemas.graph import GraphNode, GraphOut`):

```python
async def test_get_graph_calls_session_scoped_fingerprint_with_session_and_topic(
    api_client, session_factory, monkeypatch
):
    session_id = await _make_session(session_factory, topic="AI Safety")
    fake_result = GraphOut(
        nodes=[GraphNode(id="topic", label="AI Safety", type="topic", weight=1.0)],
        edges=[],
    )
    mock_fingerprint = AsyncMock(return_value=fake_result)
    monkeypatch.setattr(sessions_router, "session_scoped_fingerprint", mock_fingerprint)

    resp = api_client.get(f"/api/sessions/{session_id}/graph")

    assert resp.status_code == 200
    assert resp.json()["data"]["nodes"][0]["id"] == "topic"
    mock_fingerprint.assert_awaited_once_with("u1", session_id, "AI Safety")


async def test_get_graph_404s_for_another_users_session(api_client, session_factory):
    async with session_factory() as db:
        other = DebateSession(user_id="u2", topic="Other")
        db.add(other)
        await db.commit()
        await db.refresh(other)
        other_id = other.id

    resp = api_client.get(f"/api/sessions/{other_id}/graph")

    assert resp.status_code == 404
```

- [ ] **Step 3: Run the router tests and confirm they fail**

Run: `cd debatemind-backend && .venv/bin/pytest tests/test_sessions_router.py -v`
Expected: FAIL — the streaming test fails because `sessions_router` has no attribute `session_scoped_fingerprint` to monkeypatch; the two new `test_get_graph_*` tests fail the same way once reached (or with an `AttributeError` from `monkeypatch.setattr`, since strict mode requires the attribute to already exist... note: `monkeypatch.setattr` requires the target attribute to exist unless `raising=False`. Since the router hasn't imported `session_scoped_fingerprint` yet, this step's tests fail with `AttributeError: <module 'debatemind.routers.sessions'> has no attribute 'session_scoped_fingerprint'` — confirming the wiring in Step 4 is what's missing.

- [ ] **Step 4: Wire the router to `session_scoped_fingerprint`**

In `debatemind-backend/debatemind/routers/sessions.py`, change the import at line 31 from:

```python
from debatemind.services.graph_svc import build_graph
```

to:

```python
from debatemind.cognee.session_fingerprint import session_scoped_fingerprint
```

Change the SSE stream call (around line 308) from:

```python
        try:
            graph = await build_graph(user_id, session.topic)
            yield f"data: {json.dumps({'type': 'graph', 'data': graph.model_dump()})}\n\n"
        except Exception:
            logger.exception("build_graph failed for session %s turn %s", session_id, turn)
```

to:

```python
        try:
            graph = await session_scoped_fingerprint(user_id, session_id, session.topic)
            yield f"data: {json.dumps({'type': 'graph', 'data': graph.model_dump()})}\n\n"
        except Exception:
            logger.exception(
                "session_scoped_fingerprint failed for session %s turn %s", session_id, turn
            )
```

Change the `get_graph` endpoint (around line 544) from:

```python
    return SuccessResponse(data=await build_graph(user_id, session.topic))
```

to:

```python
    return SuccessResponse(data=await session_scoped_fingerprint(user_id, session_id, session.topic))
```

- [ ] **Step 5: Run the router tests and confirm they pass**

Run: `cd debatemind-backend && .venv/bin/pytest tests/test_sessions_router.py -v`
Expected: all tests pass, including the two new `test_get_graph_*` tests

- [ ] **Step 6: Run the full backend test suite**

Run: `cd debatemind-backend && .venv/bin/pytest -q`
Expected: all tests pass, no regressions in `test_graph_svc.py`, `test_cognee_brain_view.py`, `test_cognee_graph_view.py`, or elsewhere

- [ ] **Step 7: Commit**

```bash
git add debatemind-backend/debatemind/routers/sessions.py debatemind-backend/tests/test_sessions_router.py
git commit -m "feat: back the Cognitive Fingerprint panel with session-scoped Neo4j data"
```
