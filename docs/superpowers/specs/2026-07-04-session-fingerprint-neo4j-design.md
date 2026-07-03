# Session-scoped Cognitive Fingerprint backed by Neo4j/Cognee

## Why

`GET /api/sessions/{session_id}/graph` — which powers the in-session "Cognitive
Fingerprint" panel (`FingerprintGraph.tsx`) — currently reads exclusively from
Postgres via `debatemind/services/graph_svc.py::build_graph(user_id, topic)`. It
never touches Neo4j/Cognee.

Meanwhile the same per-exchange pattern classification is *also* written into
Neo4j as a typed `ArgumentRecord` node (`debatemind/cognee/fingerprint.py::remember_argument()`,
dispatched async via Celery from `agents/pipeline.py::_remember_node`). The
Brain Map / Knowledge Graph modal already reads this Neo4j copy
(`debatemind/cognee/brain_view.py`, `debatemind/cognee/graph_view.py`).

These are two independent writes of the same detected value, and they can drift
(`debatemind/scripts/backfill_neo4j.py` exists specifically to patch historical
drift where the Neo4j write silently failed). This change moves the session
panel onto the Neo4j/Cognee copy, matching the Brain Map's data source, while
tolerating the fact that the Neo4j write is async and may lag behind Postgres
for the most recently completed exchange(s).

**Scope decision (confirmed with user):** the panel becomes strictly
`session_id`-scoped — only patterns from this exact debate, not aggregated
across the user's other sessions on the same topic (a change from today's
Postgres behavior, which aggregates by topic across all of the user's
sessions). The unused `/api/users/me/fingerprint` endpoint and
`graph_svc.build_graph` are untouched — this change only affects
`GET /api/sessions/{session_id}/graph`.

## Data flow

New function in a new file, `debatemind-backend/debatemind/cognee/session_fingerprint.py`:

```python
async def session_scoped_fingerprint(user_id: str, session_id: str, topic: str) -> GraphOut
```

Algorithm:

1. Fetch the full Neo4j graph via `get_graph_engine().get_graph_data()` (same
   call `brain_view.py` makes). Filter to nodes where `props["type"] ==
   "ArgumentRecord"`, `props["user_id"] == user_id`, and `props["session_id"]
   == session_id`. Tally `pattern_type -> [count, wins]` (a win is
   `props["outcome"] == "Won"`). Track `neo4j_count` = total matched records.
   On any exception (engine unavailable), log and treat `neo4j_count` as `0`
   — this makes the Postgres step below reconstruct the whole session, so a
   down Neo4j degrades gracefully instead of erroring the endpoint.
2. Query Postgres for this session's exchanges: `Exchange.detected_pattern,
   Exchange.outcome WHERE session_id = :session_id AND detected_pattern IS
   NOT NULL ORDER BY created_at ASC`.
3. Take `rows[neo4j_count:]` — the exchanges past however many Neo4j already
   has — and fold their `detected_pattern`/`outcome` into the same tallies.
   This assumes Neo4j's fire-and-forget Celery writes land in roughly the
   same order exchanges were created within a session, which holds in
   practice since exchanges within one session are created sequentially.
4. Build `GraphOut` exactly as `graph_svc.build_graph` does today: one root
   `GraphNode(id="topic", label=topic[:20], type="topic", weight=1.0)`, then
   up to 8 most-common patterns (`Counter.most_common(8)`), each
   `weight = round(min(count/total*3, 0.95), 2)`, `type = "strength"` if
   `win_rate >= 0.5` else `"weakness"`, with a `GraphEdge` from `"topic"` to
   each pattern node. Same shape means `FingerprintGraph.tsx` requires no
   changes.

Two call sites in `routers/sessions.py` change from `build_graph(user_id,
session.topic)` to `session_scoped_fingerprint(user_id, session_id,
session.topic)`:

- `get_graph` (line ~544, `GET /{session_id}/graph`) — fetched on page
  load/resume.
- The per-turn SSE stream (line ~308, inside the `/message` handler) — fires
  right after the exchange is committed to Postgres and emits the `"graph"`
  event the frontend live-renders after each turn. This is the call site that
  most directly exercises the lag scenario this design handles: it runs
  before the async Celery `remember_argument_task` (dispatched from
  `agents/pipeline.py::_remember_node`, fired earlier in the same request)
  can plausibly have written the Neo4j node for the exchange that was just
  saved.

## Known limitation

The "take the tail past `neo4j_count`" merge is a count-diff heuristic, not an
exact per-exchange match. If a specific exchange's Neo4j write permanently
fails (rather than just lagging) while a later one in the same session
succeeds, the diff could misattribute which exchange is "missing." This is an
accepted tradeoff (matching the philosophy of `backfill_neo4j.py`, which
already treats this class of drift as self-healing/best-effort) — in practice
sessions have few exchanges and writes are dispatched in order, so skew is
rare and self-corrects as `backfill_neo4j.py`-style reconciliation or eventual
consistency catches up.

## Error handling

Neo4j/Cognee unavailable → caught, logged, `neo4j_count = 0`, Postgres query
alone reconstructs the full session's graph. The endpoint never 500s solely
because Neo4j is down.

## Testing

Unit tests for `session_scoped_fingerprint` (mocking `get_graph_engine` and
using a real/test Postgres session):

- Fully synced: Neo4j has all of this session's `ArgumentRecord`s → output
  matches what today's Postgres-only `build_graph` would have produced for an
  equivalent single-session fixture.
- Partially synced (drift): Neo4j has fewer records than Postgres exchanges →
  merged output includes the trailing pending pattern(s), no double-count.
- Neo4j unavailable: `get_graph_data` raises → output reconstructed entirely
  from Postgres for this session.
- Empty session: no exchanges with a `detected_pattern` yet → `GraphOut(nodes=[], edges=[])`.
