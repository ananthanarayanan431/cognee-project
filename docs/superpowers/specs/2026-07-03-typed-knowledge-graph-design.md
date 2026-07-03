# Typed Cognee knowledge graph, real recall, and true forget()

Inspired by [himanshu748/ContextFirewall](https://github.com/himanshu748/ContextFirewall)'s
`backend/app/cognee_runtime/` module: a typed `DataPoint` schema instead of free-text
blobs, a graph-view endpoint that reads Cognee's actual entity graph, and a real
forget() that deletes graph nodes + vector embeddings instead of writing a soft-delete
marker.

## Why

Debatemind's `debatemind/cognee/fingerprint.py` writes every argument, session
summary, and personal fact as a prose blob via `cognee.add(text) + cognee.cognify()`,
then recalls via `SearchType.CHUNKS` semantic search, with per-user isolation enforced
by checking `f"User: {user_id}\n" in chunk_text`. Two consequences:

1. The graph structure (which entities exist, how they connect) is entirely up to the
   LLM's inference from prose — there's no queryable, typed representation of "this
   user's argument records" for a UI to render.
2. `forget_pattern()` doesn't delete anything. It writes an additional
   `"Status: MASTERED"` text blob, and a separate helper (`filter_out_patterns`) drops
   any *retrieved chunk* whose text contains `"ArgumentPattern: {pattern}"` when the
   caller passes that pattern in `exclude_patterns`. The actual gating happens in
   Postgres (`MasteryLog` + `get_active_mastered_patterns()`), not in Cognee — the
   Cognee write is explicitly documented as "best-effort supplementary."

This change introduces a typed graph schema (mirroring ContextFirewall's
`Repo/AgentSession/SessionEvent/Memory` pattern) so that (a) a real graph-view endpoint
can render the user's actual knowledge graph, and (b) forget() can delete a precise
node + its embedding and have that deletion be authoritative for recall — which
requires moving recall off `SearchType.CHUNKS` and onto a graph+vector join over the
typed nodes, the same shape as ContextFirewall's `recall.py`.

**Scope decision (confirmed with user):** true forget applies everywhere, including
mastered patterns. Today, mastering a pattern only *hides* its evidence (Postgres gate);
after this change, mastering a pattern **permanently deletes** its `ArgumentRecord`
nodes and embeddings. `reactivate_pattern()` still clears the Postgres gate so the
opponent resumes targeting the pattern, but it no longer restores old evidence —
new `ArgumentRecord`s accumulate fresh. This is an intentional behavior change.

**Out of scope:** the SQL-based `build_graph()` / `GraphOut` schema
(`debatemind/services/graph_svc.py`) and the two existing gameplay visualizations
(`FingerprintGraph.tsx`, `BrainGraph.tsx`, driven by `MasteryLog`/`Exchange` Postgres
aggregation) are untouched. They power live, mastery-colored gameplay UI and are not
Cognee-derived today. The new graph explorer is an additional, separate view.

## Graph schema

New `debatemind/cognee/schema.py`, `DataPoint` subclasses (cognee 0.1.40,
`cognee.infrastructure.engine.DataPoint`):

```
UserProfile(user_id)                             — one per user, anchors everything
 └─ topics: list[Topic]                          — edge for graph-view convenience

Topic(user_id, name)                              — deduped per (user_id, name)

ArgumentRecord(user_id, session_id, summary,      — summary is the indexed/embedded
    pattern_type, fallacy, evidence_quality,        field: the same natural-language
    outcome, reasoning, claim_text, created_at)      sentence _argument_summary() builds
 └─ topic: Topic                                  — typed edge
 └─ owner: UserProfile                            — typed edge

SessionSummary(user_id, session_id, topic_name,
    mode, difficulty, rounds_played, win_rate,
    avg_logic, avg_evidence, avg_rhetoric,
    weak_patterns, coaching_note, created_at)
 └─ topic: Topic
 └─ owner: UserProfile

PersonalFact(user_id, session_id, fact_text, created_at)
 └─ owner: UserProfile
```

- `metadata = {"index_fields": [...]}` on each class picks the field cognee embeds
  (`ArgumentRecord.summary`, `PersonalFact.fact_text`, `SessionSummary.coaching_note`
  falling back to a synthesized summary sentence when empty — recall needs *something*
  embeddable even when the user gave no coaching note).
- `UserProfile.id` and `Topic.id` are deterministic (`uuid5` of `f"user:{user_id}"` /
  `f"topic:{user_id}:{name.lower()}"`) so repeated `add_data_points()` calls naturally
  reuse the same node instead of duplicating it — `add_data_points()` dedupes by `id`
  (confirmed via `deduplicate_nodes_and_edges` in the installed cognee package).
- `ArgumentRecord`/`SessionSummary`/`PersonalFact` get fresh UUIDs per write (each
  argument/session/fact is its own event).

## Write path (`debatemind/cognee/fingerprint.py`)

`remember_argument`, `remember_session_summary`, `remember_personal_fact` each gain an
`add_data_points([...])` call for the typed nodes, run **alongside** (not instead of)
the existing `cognee.add(prose) + cognify()` call. Two population paths, same as
ContextFirewall's `ingest.py`:

1. `add_data_points()` — deterministic typed nodes. No LLM involved, fast, gives
   forget() and the graph-view endpoint something precise to operate on.
2. `cognee.add(prose) + cognify()` — unchanged. Still grows the rich LLM-linked entity
   web (topics ↔ fallacies ↔ domains) that powers the graph explorer's "how does
   cognify connect things" view. No longer load-bearing for recall (see below).

## Recall path (rewritten)

`recall_weaknesses`, `recall_user_facts`, `recall_topic_weaknesses` move from
`SearchType.CHUNKS` to a graph+vector join, matching ContextFirewall's `recall.py`:

1. Read all `ArgumentRecord` (or `PersonalFact`) nodes from
   `get_graph_engine().get_graph_data()`, keep only `props["user_id"] == user_id`
   (exact property match — strictly safer than the current substring check on raw
   text).
2. Rank by vector search over the type's collection (cognee names vector collections
   `f"{ClassName}_{index_field}"`, e.g. `ArgumentRecord_summary`,
   `PersonalFact_fact_text`) via `get_vector_engine().search(...)`.
3. Join ranked ids back to the graph-loaded records (graph is the source of truth for
   fields; vector search only supplies relevance order) — same pattern as
   ContextFirewall's `_load_graph_memories` + `_vector_rank`.
4. `exclude_patterns` (mastery gating) becomes a plain property filter
   (`props["pattern_type"] not in exclude_patterns`) instead of text-marker matching —
   though after forget() lands, mastered patterns' nodes won't exist to filter in the
   first place. Keep the filter anyway as defense in depth (e.g. a mastery event that
   fires before its forget-delete completes).

`recall_answer`-equivalent (none exists in debatemind today) is not added — out of
scope.

## Forget path (real delete)

`forget_pattern(user_id, pattern_type)`:
1. Load graph nodes, find every `ArgumentRecord` where `user_id` and `pattern_type`
   match.
2. `await engine.delete_nodes([...])` (graph) — cascades edges per the installed
   adapter's `delete_nodes`.
3. For each deleted node, `get_vector_engine().delete_data_points("ArgumentRecord_summary", [id])`.
4. Best-effort/non-fatal: log and continue on any exception, same posture as today
   (`_mastery_prune_node` already treats this as non-critical relative to the Postgres
   `MasteryLog` write).

New `forget_personal_fact(user_id, memory_id)` — same shape, for the "forget something
I told you" personal-fact case that motivated real delete in the first place, keyed by
the `PersonalFact` node's `id`.

`reactivate_pattern_fact(user_id, pattern_type)` — simplifies to a no-op / removed
entirely, since there's nothing left to "un-mark." `mastery_svc.reactivate_pattern()`
keeps clearing the Postgres `MasteryLog` gate (that remains the reversible part); it
just stops calling into Cognee.

## Graph-view endpoint

New `debatemind/cognee/graph_view.py`:

```python
async def user_graph_view(user_id: str, limit: int = 400) -> dict:
    ...
```

- Reads `get_graph_engine().get_graph_data()`.
- Ownership: a node is included if `props.get("user_id") == user_id`, OR it is
  edge-connected to an included node (covers cognify-derived generic entities, which
  carry no `user_id` property — same adjacency-inheritance trick as
  ContextFirewall's `SessionEvent` → owning `AgentSession` namespace lookup).
- Normalizes to `{nodes: [{id, label, type, props}], edges: [{source, target, label}]}`.
  `type` is the class name (`UserProfile`, `Topic`, `ArgumentRecord`, `SessionSummary`,
  `PersonalFact`) for typed nodes, or `"Node"` for untyped cognify-derived entities —
  deliberately a different vocabulary from `GraphOut`'s `weakness/strength/mastered/topic`
  so the two graph systems are visually distinguishable and never confused.
- New router: `GET /users/me/knowledge-graph` in `debatemind/routers/users.py`, returns
  `SuccessResponse[dict]` (new schema, not `GraphOut` — different shape).

## Frontend

New `frontend/src/components/graph/KnowledgeGraphView.tsx` — d3 force graph, same
general shape as `BrainGraph.tsx` but with its own `NODE_COLOR`/`NODE_R` maps for the
new `type` vocabulary. Added as a second tab inside the existing `BrainMapModal`
(`SessionSidebar.tsx`) — tab switcher at the top of the modal, "Brain Map" (existing,
default) / "Knowledge Graph" (new). Fetches from a new `api.getKnowledgeGraph()` call.
`FingerprintGraph.tsx`, `BrainGraph.tsx`, and their data sources are untouched.

## Testing

- Unit tests for the new schema module: deterministic id generation, `add_data_points`
  round-trip on a fake/networkx graph engine (cognee's default local dev graph
  provider — no live Neo4j required for these).
- Unit tests for the ownership/adjacency filter in `graph_view.py` using constructed
  node/edge fixtures (same style as the existing `orphan_node_ids`-equivalent tests
  ContextFirewall ships for `forget.py`, adapted to this project's pytest conventions —
  see `tests/test_pipeline_mastery_prune.py` for the existing pattern of testing pure
  graph-shaped helpers without a live backend).
- Update `tests/test_pipeline_mastery_prune.py` (or add a sibling test) to cover that
  `_mastery_prune_node` now results in an actual node deletion, not just a
  `forget_pattern` prose write — mock `forget_pattern` and assert it's still called
  per mastered pattern (the pipeline-level contract doesn't change, only what
  `forget_pattern` does internally).
- Manual verification: mastery a pattern in a live session, confirm its
  `ArgumentRecord` nodes disappear from `GET /users/me/knowledge-graph` and no longer
  surface via `recall_weaknesses`.
