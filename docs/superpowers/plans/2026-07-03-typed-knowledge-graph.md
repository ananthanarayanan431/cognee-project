# Typed Knowledge Graph, Real Recall, and True Forget() Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace prose-only Cognee storage with a typed graph schema, move recall off `SearchType.CHUNKS` onto a graph+vector join over that typed schema, make `forget()` a real graph-node + embedding delete, and add a knowledge-graph explorer endpoint + frontend panel.

**Architecture:** New `debatemind/cognee/schema.py` declares typed `DataPoint` nodes (`UserProfile`, `Topic`, `ArgumentRecord`, `SessionSummary`, `PersonalFact`). `fingerprint.py`'s `remember_*` writers insert these via `add_data_points()` *alongside* the existing `cognee.add(prose) + cognify()` call (unchanged). New `debatemind/cognee/recall.py` and `debatemind/cognee/forget.py` replace the old `SearchType.CHUNKS`-based recall and soft-delete forget with a graph-read + vector-rank join, filtering strictly on each node's own `user_id` property (cognee's graph store and vector collections are global, not dataset-scoped, for `add_data_points()`-written nodes). New `debatemind/cognee/graph_view.py` + a new router endpoint expose the raw typed graph for a new frontend panel.

**Tech Stack:** FastAPI, SQLAlchemy (async), Cognee 0.1.40 (Neo4j graph backend, pgvector), pytest + pytest-asyncio (`asyncio_mode = "auto"`), Next.js 14 / React / d3 (frontend, no test runner configured).

## Global Constraints

- Cognee's typed-node graph store (`get_graph_engine()`) and per-class vector collections (`get_vector_engine()`) are **global across all users** — `add_data_points()` has no `dataset_name` scoping, unlike `cognee.add(text, dataset_name=...)`. Every reader (`recall.py`, `forget.py`, `graph_view.py`) MUST filter on the node's own `user_id` property. Never rely on query-level scoping for isolation of typed nodes.
- Mastering a pattern now **permanently deletes** its `ArgumentRecord` nodes (confirmed user decision — see `docs/superpowers/specs/2026-07-03-typed-knowledge-graph-design.md`). `reactivate_pattern()` no longer restores old evidence; it only clears the Postgres `MasteryLog` gate.
- The existing SQL-derived `build_graph()` / `GraphOut` / `FingerprintGraph.tsx` / `BrainGraph.tsx` gameplay visualizations are **out of scope** — do not modify `debatemind/services/graph_svc.py` or `debatemind/schemas/graph.py`.
- Follow existing project conventions: structured `logger.info(..., extra={...})` logging on every Cognee call (see current `fingerprint.py`), `ruff`/`ruff-format` pre-commit hooks, `pytest-asyncio` with `asyncio_mode = "auto"` (no `@pytest.mark.asyncio` decorator needed).
- Frontend has no test runner configured (`package.json` has no `test` script) — frontend tasks end with a manual dev-server verification step, not automated tests.

---

### Task 1: Typed graph schema module

**Files:**
- Create: `debatemind-backend/debatemind/cognee/schema.py`
- Test: `debatemind-backend/tests/test_cognee_schema.py`

**Interfaces:**
- Produces: `UserProfile(user_id: str)`, `Topic(user_id: str, name: str)`, `ArgumentRecord(user_id, session_id, topic_name, claim_text, pattern_type, fallacy, evidence_quality, outcome, reasoning="", summary, topic=None, owner=None)`, `SessionSummary(user_id, session_id, topic_name, mode, difficulty, rounds_played, win_rate, avg_logic, avg_evidence, avg_rhetoric, weak_patterns=[], coaching_note="", summary, topic=None, owner=None)`, `PersonalFact(user_id, session_id, fact_text, owner=None)` — all `cognee.infrastructure.engine.DataPoint` subclasses.
- Produces: `deterministic_id(*parts: str) -> uuid.UUID`, `user_profile_id(user_id: str) -> uuid.UUID`, `topic_id(user_id: str, name: str) -> uuid.UUID`.

- [ ] **Step 1: Write the failing test file**

```python
# debatemind-backend/tests/test_cognee_schema.py
"""
Unit tests for debatemind.cognee.schema — the typed DataPoint nodes that back
real forget() and the knowledge-graph view. Pure model/id-derivation tests;
no cognee storage/LLM calls.
"""

from debatemind.cognee.schema import (
    ArgumentRecord,
    PersonalFact,
    SessionSummary,
    Topic,
    UserProfile,
    deterministic_id,
    topic_id,
    user_profile_id,
)


def test_deterministic_id_is_stable_across_calls():
    a = deterministic_id("Topic", "u1", "ai safety")
    b = deterministic_id("Topic", "u1", "ai safety")
    assert a == b


def test_deterministic_id_differs_by_parts():
    a = deterministic_id("Topic", "u1", "ai safety")
    b = deterministic_id("Topic", "u2", "ai safety")
    assert a != b


def test_user_profile_id_is_stable_per_user():
    assert user_profile_id("u1") == user_profile_id("u1")
    assert user_profile_id("u1") != user_profile_id("u2")


def test_topic_id_is_case_and_whitespace_insensitive():
    assert topic_id("u1", "AI Safety") == topic_id("u1", " ai safety ")


def test_user_profile_sets_type_and_user_id():
    p = UserProfile(id=user_profile_id("u1"), user_id="u1")
    assert p.type == "UserProfile"
    assert p.user_id == "u1"


def test_topic_uses_name_as_index_field():
    t = Topic(id=topic_id("u1", "AI Safety"), user_id="u1", name="AI Safety")
    assert t.metadata["index_fields"] == ["name"]
    assert Topic.get_embeddable_data(t) == "AI Safety"


def test_argument_record_links_to_topic_and_owner():
    owner = UserProfile(id=user_profile_id("u1"), user_id="u1")
    topic = Topic(id=topic_id("u1", "AI Safety"), user_id="u1", name="AI Safety")
    record = ArgumentRecord(
        user_id="u1",
        session_id="s1",
        topic_name="AI Safety",
        claim_text="AI will take over",
        pattern_type="SlipperySlope",
        fallacy="SlipperySlope",
        evidence_quality="Weak",
        outcome="Lost",
        summary="In a debate about AI Safety, the user made a SlipperySlope argument.",
        topic=topic,
        owner=owner,
    )
    assert record.topic is topic
    assert record.owner is owner
    assert ArgumentRecord.get_embeddable_data(record) == record.summary


def test_argument_record_defaults_fallacy_and_reasoning():
    record = ArgumentRecord(
        user_id="u1",
        session_id="s1",
        topic_name="AI Safety",
        claim_text="claim",
        pattern_type="EvidenceBased",
        fallacy=None,
        evidence_quality="Strong",
        outcome="Won",
        summary="summary sentence",
    )
    assert record.fallacy is None
    assert record.reasoning == ""


def test_session_summary_index_field_is_summary():
    s = SessionSummary(
        user_id="u1",
        session_id="s1",
        topic_name="AI Safety",
        mode="chat",
        difficulty="hard",
        rounds_played=5,
        win_rate=0.4,
        avg_logic=6.0,
        avg_evidence=4.0,
        avg_rhetoric=7.0,
        summary="Over 5 rounds debating AI Safety the user won 40%.",
    )
    assert SessionSummary.get_embeddable_data(s) == s.summary
    assert s.weak_patterns == []


def test_personal_fact_index_field_is_fact_text():
    f = PersonalFact(user_id="u1", session_id="s1", fact_text="I'm a nurse in Denver")
    assert PersonalFact.get_embeddable_data(f) == "I'm a nurse in Denver"
    assert f.type == "PersonalFact"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd debatemind-backend && .venv/bin/python -m pytest tests/test_cognee_schema.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'debatemind.cognee.schema'`

- [ ] **Step 3: Write the schema module**

```python
# debatemind-backend/debatemind/cognee/schema.py
"""Typed Cognee knowledge-graph schema for debatemind.

Declaring typed DataPoint nodes (instead of relying solely on cognify's LLM to
infer structure from prose) gives forget() a precise node to delete and gives
the knowledge-graph view endpoint a stable node/edge vocabulary to render.
These nodes are written *alongside* the existing prose + cognify() calls in
fingerprint.py, which keep growing the richer, LLM-linked entity web
unchanged.

cognee 0.1.40's graph store is global across every dataset — there is no
per-dataset graph isolation the way `cognee.add(..., dataset_name=...)` scopes
prose chunks (add_data_points() has no dataset_name parameter at all). Every
typed node here therefore carries an explicit `user_id` property, and every
reader (recall.py, forget.py, graph_view.py) MUST filter on it. Never trust a
query parameter for isolation.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import SkipValidation

from cognee.infrastructure.engine import DataPoint

# Fixed, arbitrary namespace UUID for this project's deterministic ids.
_ID_NAMESPACE = uuid.UUID("f6a6e5b2-9b7b-4c1e-9c2a-1c9a7b6e5d4c")


def deterministic_id(*parts: str) -> uuid.UUID:
    """A stable UUID for the given identifying parts.

    add_data_points() dedupes graph nodes by `id` (repeated writes update the
    same node instead of creating a duplicate), so nodes meant to be reused
    across writes — a user's UserProfile, a (user, topic) Topic — must derive
    their id deterministically rather than take the DataPoint default of a
    fresh uuid4() per instantiation.
    """
    return uuid.uuid5(_ID_NAMESPACE, ":".join(parts))


def user_profile_id(user_id: str) -> uuid.UUID:
    return deterministic_id("UserProfile", user_id)


def topic_id(user_id: str, name: str) -> uuid.UUID:
    return deterministic_id("Topic", user_id, name.strip().lower())


class UserProfile(DataPoint):
    """One node per user; anchors every other typed node in their graph."""

    user_id: str
    metadata: dict = {"index_fields": []}


class Topic(DataPoint):
    """A debate topic, deduped per (user_id, name)."""

    user_id: str
    name: str
    metadata: dict = {"index_fields": ["name"]}


class ArgumentRecord(DataPoint):
    """One argument the user made — the durable weakness/strength record."""

    user_id: str
    session_id: str
    topic_name: str
    claim_text: str
    pattern_type: str
    fallacy: str | None = None
    evidence_quality: str
    outcome: str
    reasoning: str = ""
    summary: str  # natural-language sentence; the embedded/indexed field
    topic: SkipValidation[Any] = None  # -> Topic (typed edge)
    owner: SkipValidation[Any] = None  # -> UserProfile (typed edge)
    metadata: dict = {"index_fields": ["summary"]}


class SessionSummary(DataPoint):
    """One per debate session — thinking-style + weak-pattern rollup."""

    user_id: str
    session_id: str
    topic_name: str
    mode: str
    difficulty: str
    rounds_played: int
    win_rate: float
    avg_logic: float
    avg_evidence: float
    avg_rhetoric: float
    weak_patterns: list[str] = []
    coaching_note: str = ""
    summary: str
    topic: SkipValidation[Any] = None  # -> Topic
    owner: SkipValidation[Any] = None  # -> UserProfile
    metadata: dict = {"index_fields": ["summary"]}


class PersonalFact(DataPoint):
    """A personal fact the user revealed (name, likes, background)."""

    user_id: str
    session_id: str
    fact_text: str
    owner: SkipValidation[Any] = None  # -> UserProfile
    metadata: dict = {"index_fields": ["fact_text"]}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd debatemind-backend && .venv/bin/python -m pytest tests/test_cognee_schema.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
cd debatemind-backend
git add debatemind/cognee/schema.py tests/test_cognee_schema.py
git commit -m "feat: add typed Cognee DataPoint schema for the knowledge graph"
```

---

### Task 2: Structured pattern filtering in `_base.py`

**Files:**
- Modify: `debatemind-backend/debatemind/cognee/_base.py:46-57`
- Test: `debatemind-backend/tests/test_cognee_base.py` (new)

**Interfaces:**
- Consumes: nothing new.
- Produces: `filter_out_patterns(items: list[dict], patterns: set[str] | None) -> list[dict]` — same signature as today, but now matches on `item.get("pattern_type")` instead of a text-marker substring. Callers: `debatemind/agents/opponent.py:68` (unchanged call site), `debatemind/cognee/recall.py` (Task 4, new call site).

- [ ] **Step 1: Write the failing test**

```python
# debatemind-backend/tests/test_cognee_base.py
"""
Unit tests for debatemind.cognee._base.filter_out_patterns — the mastery
exclusion filter shared by recall.py and agents/opponent.py's cache re-filter.
"""

from debatemind.cognee._base import filter_out_patterns


def test_filter_out_patterns_drops_matching_pattern_type():
    items = [
        {"text": "a", "pattern_type": "StrawMan"},
        {"text": "b", "pattern_type": "AdHominem"},
    ]
    result = filter_out_patterns(items, {"StrawMan"})
    assert result == [{"text": "b", "pattern_type": "AdHominem"}]


def test_filter_out_patterns_returns_all_when_patterns_falsy():
    items = [{"text": "a", "pattern_type": "StrawMan"}]
    assert filter_out_patterns(items, None) == items
    assert filter_out_patterns(items, set()) == items


def test_filter_out_patterns_keeps_items_with_no_pattern_type():
    """Session-summary records carry no pattern_type — always kept."""
    items = [{"text": "session summary"}]
    assert filter_out_patterns(items, {"StrawMan"}) == items
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd debatemind-backend && .venv/bin/python -m pytest tests/test_cognee_base.py -v`
Expected: FAIL — `test_filter_out_patterns_drops_matching_pattern_type` fails because the current implementation matches on `"ArgumentPattern: {pattern}"` substring in `text`, not `pattern_type`, so `{"text": "a", "pattern_type": "StrawMan"}` (no marker in `text`) is NOT dropped.

- [ ] **Step 3: Rewrite `filter_out_patterns`**

In `debatemind/cognee/_base.py`, replace:

```python
def filter_out_patterns(items: list[dict], patterns: set[str] | None) -> list[dict]:
    """Drop recalled argument records whose ArgumentPattern is a mastered pattern.

    This is what makes forget()/mastery behaviourally real: once a pattern is
    mastered, its weakness records stop being fed to the opponent, so the AI
    demonstrably stops targeting it. Session-summary records are kept (they carry
    topic-level context, not a single exploitable pattern).
    """
    if not patterns:
        return items
    markers = tuple(f"ArgumentPattern: {p}" for p in patterns)
    return [it for it in items if not any(m in it.get("text", "") for m in markers)]
```

with:

```python
def filter_out_patterns(items: list[dict], patterns: set[str] | None) -> list[dict]:
    """Drop recalled argument records whose pattern_type is a mastered pattern.

    This is what makes forget()/mastery behaviourally real: once a pattern is
    mastered, its weakness records stop being fed to the opponent, so the AI
    demonstrably stops targeting it. Matches the structured `pattern_type` field
    recall.py attaches to every ArgumentRecord dict (not a text marker) — records
    with no `pattern_type` key (e.g. personal facts) are always kept.
    """
    if not patterns:
        return items
    return [it for it in items if it.get("pattern_type") not in patterns]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd debatemind-backend && .venv/bin/python -m pytest tests/test_cognee_base.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
cd debatemind-backend
git add debatemind/cognee/_base.py tests/test_cognee_base.py
git commit -m "refactor: match filter_out_patterns on pattern_type field, not text marker"
```

---

### Task 3: Typed-node writes in the `remember_*` functions

**Files:**
- Modify: `debatemind-backend/debatemind/cognee/fingerprint.py` (imports at top; `remember_argument`, `remember_session_summary`, `remember_personal_fact`)
- Modify: `debatemind-backend/tests/test_cognee_svc.py`

**Interfaces:**
- Consumes: `debatemind.cognee.schema.{UserProfile, Topic, ArgumentRecord, SessionSummary, PersonalFact, user_profile_id, topic_id}` (Task 1), `cognee.tasks.storage.add_data_points`.
- Produces: `remember_argument`/`remember_session_summary`/`remember_personal_fact` keep their existing signatures and prose-write behavior; each additionally calls `add_data_points([...])` with the typed nodes, non-fatally on failure.

- [ ] **Step 1: Update the failing tests**

In `debatemind-backend/tests/test_cognee_svc.py`, add these four tests (anywhere after the existing imports; no new imports needed — `AsyncMock` is already imported):

```python
async def test_remember_argument_writes_typed_argument_record(monkeypatch):
    monkeypatch.setattr(fingerprint_mod.cognee, "add", AsyncMock())
    monkeypatch.setattr(fingerprint_mod.cognee, "cognify", AsyncMock())
    add_data_points_mock = AsyncMock()
    monkeypatch.setattr(fingerprint_mod, "add_data_points", add_data_points_mock)

    await remember_argument(
        user_id="u1",
        session_id="s1",
        topic="AI Safety",
        claim_text="AI will inevitably take over",
        pattern_type="SlipperySlope",
        fallacy="SlipperySlope",
        evidence_quality="Weak",
        outcome="Lost",
        reasoning="Asserts an extreme outcome without a causal chain.",
    )

    add_data_points_mock.assert_awaited_once()
    (nodes,), _ = add_data_points_mock.call_args
    types = {n.type for n in nodes}
    assert types == {"UserProfile", "Topic", "ArgumentRecord"}
    record = next(n for n in nodes if n.type == "ArgumentRecord")
    assert record.user_id == "u1"
    assert record.session_id == "s1"
    assert record.topic_name == "AI Safety"
    assert record.pattern_type == "SlipperySlope"
    assert record.fallacy == "SlipperySlope"
    assert record.evidence_quality == "Weak"
    assert record.outcome == "Lost"
    assert 'In a debate about "AI Safety"' in record.summary
    assert record.topic.name == "AI Safety"
    assert record.owner.user_id == "u1"


async def test_remember_argument_typed_write_failure_does_not_raise(monkeypatch):
    monkeypatch.setattr(fingerprint_mod.cognee, "add", AsyncMock())
    monkeypatch.setattr(fingerprint_mod.cognee, "cognify", AsyncMock())
    monkeypatch.setattr(
        fingerprint_mod, "add_data_points", AsyncMock(side_effect=RuntimeError("boom"))
    )

    # Must not raise: the prose write is the load-bearing path, the typed node
    # is best-effort supplementary.
    await remember_argument(
        user_id="u1",
        session_id="s1",
        topic="AI Safety",
        claim_text="claim",
        pattern_type="EvidenceBased",
        fallacy=None,
        evidence_quality="Strong",
        outcome="Won",
    )


async def test_remember_session_summary_writes_typed_session_summary(monkeypatch):
    monkeypatch.setattr(fingerprint_mod.cognee, "add", AsyncMock())
    monkeypatch.setattr(fingerprint_mod.cognee, "cognify", AsyncMock())
    add_data_points_mock = AsyncMock()
    monkeypatch.setattr(fingerprint_mod, "add_data_points", add_data_points_mock)

    await remember_session_summary(
        user_id="u1",
        session_id="s1",
        topic="AI regulation",
        mode="chat",
        difficulty="hard",
        rounds_played=5,
        win_rate=0.4,
        avg_logic=6.0,
        avg_evidence=4.0,
        avg_rhetoric=7.0,
        weak_patterns=["SlipperySlope", "StrawMan"],
    )

    (nodes,), _ = add_data_points_mock.call_args
    summary = next(n for n in nodes if n.type == "SessionSummary")
    assert summary.user_id == "u1"
    assert summary.topic_name == "AI regulation"
    assert summary.rounds_played == 5
    assert summary.weak_patterns == ["SlipperySlope", "StrawMan"]
    assert "the user won" in summary.summary


async def test_remember_personal_fact_writes_typed_personal_fact(monkeypatch):
    monkeypatch.setattr(fingerprint_mod.cognee, "add", AsyncMock())
    monkeypatch.setattr(fingerprint_mod.cognee, "cognify", AsyncMock())
    add_data_points_mock = AsyncMock()
    monkeypatch.setattr(fingerprint_mod, "add_data_points", add_data_points_mock)

    from debatemind.cognee.fingerprint import remember_personal_fact

    await remember_personal_fact("u1", "s1", "I'm a nurse in Denver")

    (nodes,), _ = add_data_points_mock.call_args
    fact = next(n for n in nodes if n.type == "PersonalFact")
    assert fact.user_id == "u1"
    assert fact.session_id == "s1"
    assert fact.fact_text == "I'm a nurse in Denver"
    assert fact.owner.user_id == "u1"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd debatemind-backend && .venv/bin/python -m pytest tests/test_cognee_svc.py -v -k "typed"`
Expected: FAIL — `AttributeError: <module 'debatemind.cognee.fingerprint'> does not have the attribute 'add_data_points'` (not imported yet) or `assert_awaited_once()` failures.

- [ ] **Step 3: Add imports to `fingerprint.py`**

At the top of `debatemind-backend/debatemind/cognee/fingerprint.py`, change:

```python
import cognee
from cognee.api.v1.search.search import SearchType

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
```

to:

```python
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
```

(`SearchType`, `filter_out_patterns`, `result_text` become unused by the end of Task 4/6's cleanup — leave them for now, Task 6 removes them along with the functions that use them.)

- [ ] **Step 4: Add the typed write to `remember_argument`**

In `remember_argument`, change:

```python
    if reasoning:
        text += f"Reasoning: {reasoning}\n"
    text += (
        "Summary: "
        + _argument_summary(topic, pattern_type, fallacy, evidence_quality, outcome, reasoning)
        + "\n"
    )
    dataset = fingerprint_dataset(user_id)
```

to:

```python
    if reasoning:
        text += f"Reasoning: {reasoning}\n"
    summary = _argument_summary(topic, pattern_type, fallacy, evidence_quality, outcome, reasoning)
    text += "Summary: " + summary + "\n"
    dataset = fingerprint_dataset(user_id)
```

Then, at the very end of `remember_argument` (after the existing `cognee.cognify` logging block), add:

```python
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
```

- [ ] **Step 5: Add the typed write to `remember_session_summary`**

In `remember_session_summary`, change:

```python
    if coaching_note:
        text += f"CoachingNote: {coaching_note}\n"
    # Prose sentence weaving topic (-> KnowledgeDomain), thinking style, and weak
    # patterns so cognify can extract domain-linked, typed nodes rather than
    # scoring the terse markers alone.
    text += (
        "Summary: "
        f'Over {rounds_played} rounds debating "{topic}" in {mode} mode at '
        f"{difficulty} difficulty, the user won {win_rate:.0%} of exchanges. "
        f"Their thinking style leaned Logic {avg_logic:.1f}, Evidence {avg_evidence:.1f}, "
        f"Rhetoric {avg_rhetoric:.1f}. Recurring weak patterns: {patterns_str}.\n"
    )

    dataset = fingerprint_dataset(user_id)
```

to:

```python
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
```

Then, at the very end of `remember_session_summary` (after its `cognee.cognify` logging block), add:

```python
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
        logger.exception(
            "add_data_points failed for SessionSummary user %s — continuing", user_id
        )
```

- [ ] **Step 6: Add the typed write to `remember_personal_fact`**

At the very end of `remember_personal_fact` (after its `cognee.cognify` logging block), add:

```python
    try:
        owner = UserProfile(id=user_profile_id(user_id), user_id=user_id)
        fact = PersonalFact(
            user_id=user_id, session_id=session_id, fact_text=fact_text, owner=owner
        )
        await add_data_points([owner, fact])
    except Exception:
        logger.exception(
            "add_data_points failed for PersonalFact user %s — continuing", user_id
        )
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `cd debatemind-backend && .venv/bin/python -m pytest tests/test_cognee_svc.py -v`
Expected: PASS (all tests, including the pre-existing ones — the prose-write assertions are untouched)

- [ ] **Step 8: Commit**

```bash
cd debatemind-backend
git add debatemind/cognee/fingerprint.py tests/test_cognee_svc.py
git commit -m "feat: write typed graph nodes alongside prose in remember_argument/session_summary/personal_fact"
```

---

### Task 4: `recall.py` — graph+vector join recall

**Files:**
- Create: `debatemind-backend/debatemind/cognee/recall.py`
- Test: `debatemind-backend/tests/test_cognee_recall.py`

**Interfaces:**
- Consumes: `debatemind.cognee._base.{SEARCH_TIMEOUT, elapsed_ms, filter_out_patterns, preview}` (Task 2), no schema import needed (works off raw graph node property dicts).
- Produces: `owned_nodes(node_type: str, user_id: str) -> dict[str, dict]`, `recall_weaknesses(user_id: str, exclude_patterns: set[str] | None = None) -> list[dict]`, `recall_topic_weaknesses(user_id: str, topic: str, exclude_patterns: set[str] | None = None) -> list[dict]`, `recall_user_facts(user_id: str, topic: str = "") -> list[dict]`. Each returned dict has a `"text"` key (for prompt-building call sites) and, for argument records, a `"pattern_type"` key (for `filter_out_patterns`). `owned_nodes` is reused by `forget.py` (Task 5).

- [ ] **Step 1: Write the failing test file**

```python
# debatemind-backend/tests/test_cognee_recall.py
"""
Unit tests for debatemind.cognee.recall — the graph+vector join that replaced
SearchType.CHUNKS search. get_graph_engine()/get_vector_engine() are mocked;
no real Cognee storage/LLM calls happen here.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from debatemind.cognee.recall import (
    owned_nodes,
    recall_topic_weaknesses,
    recall_user_facts,
    recall_weaknesses,
)


def _node(node_type: str, **props):
    return (str(uuid4()), {"type": node_type, **props})


class _FakeGraphEngine:
    def __init__(self, nodes):
        self._nodes = nodes

    async def get_graph_data(self):
        return self._nodes, []


class _FakeScoredResult:
    def __init__(self, node_id: str):
        self.id = node_id


def _patch_graph_engine(monkeypatch, nodes):
    async def fake_get_graph_engine():
        return _FakeGraphEngine(nodes)

    monkeypatch.setattr(
        "cognee.infrastructure.databases.graph.get_graph_engine", fake_get_graph_engine
    )


def _patch_vector_engine(monkeypatch, ranked_ids):
    fake_engine = MagicMock()
    fake_engine.search = AsyncMock(return_value=[_FakeScoredResult(i) for i in ranked_ids])
    monkeypatch.setattr(
        "cognee.infrastructure.databases.vector.get_vector_engine", lambda: fake_engine
    )
    return fake_engine


async def test_owned_nodes_filters_by_type_and_user_id():
    u1_id, u1_node = _node("ArgumentRecord", user_id="u1", pattern_type="StrawMan")
    u2_id, u2_node = _node("ArgumentRecord", user_id="u2", pattern_type="StrawMan")
    topic_id_, topic_node = _node("Topic", user_id="u1", name="AI")
    engine = _FakeGraphEngine([(u1_id, u1_node), (u2_id, u2_node), (topic_id_, topic_node)])

    with patch(
        "cognee.infrastructure.databases.graph.get_graph_engine",
        new=AsyncMock(return_value=engine),
    ):
        result = await owned_nodes("ArgumentRecord", "u1")

    assert result == {u1_id: u1_node}


async def test_recall_weaknesses_ranks_by_vector_search(monkeypatch):
    id_a, node_a = _node(
        "ArgumentRecord", user_id="u1", pattern_type="StrawMan", summary="straw man summary"
    )
    id_b, node_b = _node(
        "ArgumentRecord", user_id="u1", pattern_type="AdHominem", summary="ad hominem summary"
    )
    _patch_graph_engine(monkeypatch, [(id_a, node_a), (id_b, node_b)])
    _patch_vector_engine(monkeypatch, [id_b, id_a])

    results = await recall_weaknesses("u1")

    assert [r["text"] for r in results] == ["ad hominem summary", "straw man summary"]
    assert [r["pattern_type"] for r in results] == ["AdHominem", "StrawMan"]


async def test_recall_weaknesses_excludes_mastered_patterns(monkeypatch):
    id_a, node_a = _node(
        "ArgumentRecord", user_id="u1", pattern_type="StrawMan", summary="straw man summary"
    )
    id_b, node_b = _node(
        "ArgumentRecord", user_id="u1", pattern_type="AdHominem", summary="ad hominem summary"
    )
    _patch_graph_engine(monkeypatch, [(id_a, node_a), (id_b, node_b)])
    _patch_vector_engine(monkeypatch, [id_a, id_b])

    results = await recall_weaknesses("u1", exclude_patterns={"StrawMan"})

    assert [r["text"] for r in results] == ["ad hominem summary"]


async def test_recall_weaknesses_isolates_by_user_id(monkeypatch):
    id_a, node_a = _node(
        "ArgumentRecord", user_id="u1", pattern_type="StrawMan", summary="mine"
    )
    id_b, node_b = _node(
        "ArgumentRecord", user_id="u2", pattern_type="StrawMan", summary="not mine"
    )
    _patch_graph_engine(monkeypatch, [(id_a, node_a), (id_b, node_b)])
    _patch_vector_engine(monkeypatch, [id_b, id_a])

    results = await recall_weaknesses("u1")

    assert [r["text"] for r in results] == ["mine"]


async def test_recall_weaknesses_falls_back_to_unranked_when_vector_search_misses(monkeypatch):
    id_a, node_a = _node(
        "ArgumentRecord", user_id="u1", pattern_type="StrawMan", summary="only record"
    )
    _patch_graph_engine(monkeypatch, [(id_a, node_a)])
    # Vector search returns ids that don't belong to this user (crowded out globally).
    _patch_vector_engine(monkeypatch, [str(uuid4())])

    results = await recall_weaknesses("u1")

    assert [r["text"] for r in results] == ["only record"]


async def test_recall_weaknesses_returns_empty_when_nothing_owned(monkeypatch):
    _patch_graph_engine(monkeypatch, [])
    vector_engine = _patch_vector_engine(monkeypatch, [])

    results = await recall_weaknesses("u1")

    assert results == []
    vector_engine.search.assert_not_awaited()


async def test_recall_topic_weaknesses_filters_by_topic_name(monkeypatch):
    id_a, node_a = _node(
        "ArgumentRecord",
        user_id="u1",
        pattern_type="StrawMan",
        topic_name="AI Safety",
        summary="about AI",
    )
    id_b, node_b = _node(
        "ArgumentRecord",
        user_id="u1",
        pattern_type="AdHominem",
        topic_name="Climate Policy",
        summary="about climate",
    )
    _patch_graph_engine(monkeypatch, [(id_a, node_a), (id_b, node_b)])
    _patch_vector_engine(monkeypatch, [id_a])

    results = await recall_topic_weaknesses("u1", "AI Safety")

    assert [r["text"] for r in results] == ["about AI"]


async def test_recall_topic_weaknesses_is_case_insensitive(monkeypatch):
    id_a, node_a = _node(
        "ArgumentRecord",
        user_id="u1",
        pattern_type="StrawMan",
        topic_name="AI Safety",
        summary="about AI",
    )
    _patch_graph_engine(monkeypatch, [(id_a, node_a)])
    _patch_vector_engine(monkeypatch, [id_a])

    results = await recall_topic_weaknesses("u1", "ai safety")

    assert [r["text"] for r in results] == ["about AI"]


async def test_recall_user_facts_returns_owned_facts(monkeypatch):
    id_a, node_a = _node("PersonalFact", user_id="u1", fact_text="I'm a nurse")
    id_b, node_b = _node("PersonalFact", user_id="u2", fact_text="not mine")
    _patch_graph_engine(monkeypatch, [(id_a, node_a), (id_b, node_b)])
    _patch_vector_engine(monkeypatch, [id_a, id_b])

    results = await recall_user_facts("u1")

    assert [r["text"] for r in results] == ["I'm a nurse"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd debatemind-backend && .venv/bin/python -m pytest tests/test_cognee_recall.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'debatemind.cognee.recall'`

- [ ] **Step 3: Write `recall.py`**

```python
# debatemind-backend/debatemind/cognee/recall.py
"""Recall — retrieve this user's typed ArgumentRecord/PersonalFact nodes from
Cognee's graph for the opponent and progress views, ranked by relevance.

cognee 0.1.40's graph store and per-class vector collections are GLOBAL across
every user (there is no dataset-scoped graph query the way
`cognee.search(..., datasets=[...])` scopes prose CHUNKS search). So isolation
here is enforced by filtering on each node's own `user_id` property after
loading it — never by trusting the vector search's result order, which only
supplies a relevance ranking over an already-owned candidate set (same
graph+vector join shape as ContextFirewall's recall.py).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

from debatemind.cognee._base import SEARCH_TIMEOUT, elapsed_ms, filter_out_patterns, preview

logger = logging.getLogger(__name__)

# Fetched from the GLOBAL per-class vector collection, then filtered down to
# this user's owned nodes — a generous limit so this user's own records are
# likely present in the ranked set even when many other users share the same
# collection. This is a ranking aid only; ownership filtering (below) is what
# actually enforces isolation.
_VECTOR_TOP_K = 100


def _node_props(entry: Any) -> tuple[str, dict]:
    """Normalize a get_graph_data() node entry to (id, properties)."""
    if isinstance(entry, tuple):
        nid, props = entry[0], entry[1]
    else:
        props, nid = entry, entry.get("id")
    return str(nid), dict(props or {})


async def owned_nodes(node_type: str, user_id: str) -> dict[str, dict]:
    """All graph nodes of `node_type` owned by `user_id`, keyed by node id."""
    from cognee.infrastructure.databases.graph import get_graph_engine

    try:
        engine = await get_graph_engine()
        nodes, _edges = await engine.get_graph_data()
    except Exception:
        logger.exception("get_graph_data failed while loading %s for user %s", node_type, user_id)
        return {}

    owned: dict[str, dict] = {}
    for entry in nodes:
        nid, props = _node_props(entry)
        if props.get("type") == node_type and props.get("user_id") == user_id:
            owned[nid] = props
    return owned


async def _vector_rank(collection: str, query: str, limit: int) -> list[str]:
    """Node ids from `collection`, ordered by relevance to `query` (best effort)."""
    from cognee.infrastructure.databases.vector import get_vector_engine

    engine = get_vector_engine()  # sync factory -> handle
    try:
        results = await engine.search(collection_name=collection, query_text=query, limit=limit)
    except Exception:
        logger.warning("vector search failed for collection %s", collection, exc_info=True)
        return []
    return [str(r.id) for r in results]


async def _rank_and_build(
    owned: dict[str, dict],
    *,
    collection: str,
    query: str,
    top_k: int,
    to_record: Callable[[str, dict], dict],
) -> list[dict]:
    if not owned:
        return []

    try:
        ranked_ids = await asyncio.wait_for(
            _vector_rank(collection, query, _VECTOR_TOP_K), timeout=SEARCH_TIMEOUT
        )
    except asyncio.TimeoutError:
        ranked_ids = []

    ordered: list[dict] = []
    seen: set[str] = set()
    for nid in ranked_ids:
        if nid in owned and nid not in seen:
            ordered.append(to_record(nid, owned[nid]))
            seen.add(nid)
    if not ordered:
        # Vector search's global top_k didn't surface any of this user's ids
        # (crowded out by other users' records) — fall back to the owned set
        # unranked rather than returning nothing.
        ordered = [to_record(nid, props) for nid, props in owned.items()]
    return ordered[:top_k]


def _argument_record(node_id: str, props: dict) -> dict:
    return {
        "node_id": node_id,
        "text": props.get("summary", ""),
        "pattern_type": props.get("pattern_type"),
        "fallacy": props.get("fallacy"),
        "outcome": props.get("outcome"),
        "session_id": props.get("session_id"),
    }


def _fact_record(node_id: str, props: dict) -> dict:
    return {"node_id": node_id, "text": props.get("fact_text", "")}


async def recall_weaknesses(user_id: str, exclude_patterns: set[str] | None = None) -> list[dict]:
    t0 = time.monotonic()
    owned = await owned_nodes("ArgumentRecord", user_id)
    items = await _rank_and_build(
        owned,
        collection="ArgumentRecord_summary",
        query="fallacy weak evidence poor argument outcome lost",
        top_k=10,
        to_record=_argument_record,
    )
    items = filter_out_patterns(items, exclude_patterns)
    logger.info(
        "cognee.recall_weaknesses ok",
        extra={
            "event": "cognee.recall_weaknesses.ok",
            "user_id": user_id,
            "owned": len(owned),
            "results": len(items),
            "excluded_patterns": sorted(exclude_patterns) if exclude_patterns else [],
            "elapsed_ms": elapsed_ms(t0),
        },
    )
    logger.debug(
        "cognee.recall_weaknesses ok preview",
        extra={"results_preview": [preview(it["text"], 120) for it in items[:3]]},
    )
    return items


async def recall_topic_weaknesses(
    user_id: str, topic: str, exclude_patterns: set[str] | None = None
) -> list[dict]:
    t0 = time.monotonic()
    owned = await owned_nodes("ArgumentRecord", user_id)
    normalized_topic = topic.strip().lower()
    topic_owned = {
        nid: props
        for nid, props in owned.items()
        if (props.get("topic_name") or "").strip().lower() == normalized_topic
    }
    items = await _rank_and_build(
        topic_owned,
        collection="ArgumentRecord_summary",
        query=f"topic {topic} weak poor outcome lost needs improvement",
        top_k=5,
        to_record=_argument_record,
    )
    items = filter_out_patterns(items, exclude_patterns)
    logger.info(
        "cognee.recall_topic_weaknesses ok",
        extra={
            "event": "cognee.recall_topic_weaknesses.ok",
            "user_id": user_id,
            "topic": topic,
            "owned": len(topic_owned),
            "results": len(items),
            "elapsed_ms": elapsed_ms(t0),
        },
    )
    return items


async def recall_user_facts(user_id: str, topic: str = "") -> list[dict]:
    t0 = time.monotonic()
    owned = await owned_nodes("PersonalFact", user_id)
    query = (
        f"personal facts about the user relevant to {topic}: "
        "preferences, background, interests, dislikes, occupation"
        if topic
        else "personal facts about the user: preferences, background, interests, dislikes"
    )
    items = await _rank_and_build(
        owned, collection="PersonalFact_fact_text", query=query, top_k=5, to_record=_fact_record
    )
    logger.info(
        "cognee.recall_user_facts ok",
        extra={
            "event": "cognee.recall_user_facts.ok",
            "user_id": user_id,
            "topic": topic,
            "owned": len(owned),
            "results": len(items),
            "elapsed_ms": elapsed_ms(t0),
        },
    )
    return items
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd debatemind-backend && .venv/bin/python -m pytest tests/test_cognee_recall.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
cd debatemind-backend
git add debatemind/cognee/recall.py tests/test_cognee_recall.py
git commit -m "feat: add graph+vector join recall over typed nodes"
```

---

### Task 5: `forget.py` — real graph + embedding deletion

**Files:**
- Create: `debatemind-backend/debatemind/cognee/forget.py`
- Test: `debatemind-backend/tests/test_cognee_forget.py`

**Interfaces:**
- Consumes: `debatemind.cognee.recall.owned_nodes` (Task 4).
- Produces: `forget_pattern(user_id: str, pattern_type: str) -> None`, `forget_personal_fact(user_id: str, node_id: str) -> dict` (returns `{"node_id": ..., "status": "forgotten" | "not_found"}`).

- [ ] **Step 1: Write the failing test file**

```python
# debatemind-backend/tests/test_cognee_forget.py
"""
Unit tests for debatemind.cognee.forget — real graph-node + vector-embedding
deletion. get_graph_engine()/get_vector_engine()/recall.owned_nodes are
mocked; no real Cognee storage calls happen here.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from debatemind.cognee.forget import forget_pattern, forget_personal_fact


async def test_forget_pattern_deletes_matching_argument_records():
    owned = {
        "id-a": {"type": "ArgumentRecord", "user_id": "u1", "pattern_type": "StrawMan"},
        "id-b": {"type": "ArgumentRecord", "user_id": "u1", "pattern_type": "AdHominem"},
    }
    graph_engine = MagicMock()
    graph_engine.delete_nodes = AsyncMock()
    vector_engine = MagicMock()
    vector_engine.delete_data_points = AsyncMock()

    with (
        patch("debatemind.cognee.forget.owned_nodes", new=AsyncMock(return_value=owned)),
        patch(
            "cognee.infrastructure.databases.graph.get_graph_engine",
            new=AsyncMock(return_value=graph_engine),
        ),
        patch(
            "cognee.infrastructure.databases.vector.get_vector_engine",
            return_value=vector_engine,
        ),
    ):
        await forget_pattern("u1", "StrawMan")

    graph_engine.delete_nodes.assert_awaited_once_with(["id-a"])
    vector_engine.delete_data_points.assert_awaited_once_with("ArgumentRecord_summary", ["id-a"])


async def test_forget_pattern_noop_when_nothing_matches():
    graph_engine = MagicMock()
    graph_engine.delete_nodes = AsyncMock()

    with (
        patch("debatemind.cognee.forget.owned_nodes", new=AsyncMock(return_value={})),
        patch(
            "cognee.infrastructure.databases.graph.get_graph_engine",
            new=AsyncMock(return_value=graph_engine),
        ),
    ):
        await forget_pattern("u1", "StrawMan")

    graph_engine.delete_nodes.assert_not_awaited()


async def test_forget_pattern_vector_delete_failure_does_not_raise():
    owned = {"id-a": {"type": "ArgumentRecord", "user_id": "u1", "pattern_type": "StrawMan"}}
    graph_engine = MagicMock()
    graph_engine.delete_nodes = AsyncMock()
    vector_engine = MagicMock()
    vector_engine.delete_data_points = AsyncMock(side_effect=RuntimeError("boom"))

    with (
        patch("debatemind.cognee.forget.owned_nodes", new=AsyncMock(return_value=owned)),
        patch(
            "cognee.infrastructure.databases.graph.get_graph_engine",
            new=AsyncMock(return_value=graph_engine),
        ),
        patch(
            "cognee.infrastructure.databases.vector.get_vector_engine",
            return_value=vector_engine,
        ),
    ):
        await forget_pattern("u1", "StrawMan")  # must not raise

    graph_engine.delete_nodes.assert_awaited_once_with(["id-a"])


async def test_forget_personal_fact_deletes_owned_fact():
    owned = {"id-a": {"type": "PersonalFact", "user_id": "u1", "fact_text": "I'm a nurse"}}
    graph_engine = MagicMock()
    graph_engine.delete_nodes = AsyncMock()
    vector_engine = MagicMock()
    vector_engine.delete_data_points = AsyncMock()

    with (
        patch("debatemind.cognee.forget.owned_nodes", new=AsyncMock(return_value=owned)),
        patch(
            "cognee.infrastructure.databases.graph.get_graph_engine",
            new=AsyncMock(return_value=graph_engine),
        ),
        patch(
            "cognee.infrastructure.databases.vector.get_vector_engine",
            return_value=vector_engine,
        ),
    ):
        result = await forget_personal_fact("u1", "id-a")

    assert result == {"node_id": "id-a", "status": "forgotten"}
    graph_engine.delete_nodes.assert_awaited_once_with(["id-a"])
    vector_engine.delete_data_points.assert_awaited_once_with("PersonalFact_fact_text", ["id-a"])


async def test_forget_personal_fact_returns_not_found_for_unowned_node():
    with patch("debatemind.cognee.forget.owned_nodes", new=AsyncMock(return_value={})):
        result = await forget_personal_fact("u1", "someone-elses-node")

    assert result == {"node_id": "someone-elses-node", "status": "not_found"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd debatemind-backend && .venv/bin/python -m pytest tests/test_cognee_forget.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'debatemind.cognee.forget'`

- [ ] **Step 3: Write `forget.py`**

```python
# debatemind-backend/debatemind/cognee/forget.py
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
    logger.info(
        "forget_personal_fact deleted node", extra={"user_id": user_id, "node_id": node_id}
    )
    return {"node_id": node_id, "status": "forgotten"}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd debatemind-backend && .venv/bin/python -m pytest tests/test_cognee_forget.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
cd debatemind-backend
git add debatemind/cognee/forget.py tests/test_cognee_forget.py
git commit -m "feat: real forget() — delete graph nodes and vector embeddings"
```

---

### Task 6: Remove the old prose-marker recall/forget/reactivate code

**Files:**
- Modify: `debatemind-backend/debatemind/cognee/fingerprint.py` (remove `recall_user_facts`, `recall_weaknesses`, `recall_topic_weaknesses`, `forget_pattern`, `reactivate_pattern_fact`; remove now-unused imports)
- Modify: `debatemind-backend/debatemind/cognee/__init__.py`
- Modify: `debatemind-backend/debatemind/services/mastery_svc.py`
- Modify: `debatemind-backend/tests/test_cognee_svc.py` (remove now-obsolete tests, superseded by Task 4/5's test files)
- Modify: `debatemind-backend/tests/test_mastery_svc.py`

**Interfaces:**
- Consumes: `debatemind.cognee.recall.{recall_weaknesses, recall_topic_weaknesses, recall_user_facts}` (Task 4), `debatemind.cognee.forget.{forget_pattern, forget_personal_fact}` (Task 5).
- Produces: `debatemind.cognee.__init__`'s public surface drops `reactivate_pattern_fact`; `mastery_svc.reactivate_pattern` no longer touches Cognee.

- [ ] **Step 1: Delete the superseded functions from `fingerprint.py`**

Remove these five functions from `debatemind-backend/debatemind/cognee/fingerprint.py` in their entirety: `recall_user_facts`, `recall_weaknesses`, `recall_topic_weaknesses`, `forget_pattern`, `reactivate_pattern_fact`. What remains in the file: `_argument_summary`, `remember_argument`, `remember_session_summary`, `remember_personal_fact`, `improve_fingerprint`.

Update the top-of-file imports — change:

```python
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
```

to:

```python
import cognee
from cognee.tasks.storage import add_data_points

from debatemind.cognee._base import ADD_TIMEOUT, COGNIFY_TIMEOUT, elapsed_ms, fingerprint_dataset, ontology_file
```

(`SearchType`, `SEARCH_TIMEOUT`, `filter_out_patterns`, `preview`, `result_text` were only used by the functions just deleted.)

- [ ] **Step 2: Update `debatemind/cognee/__init__.py`**

Replace the entire file with:

```python
"""Public API for all cognee operations.

Import from here rather than the sub-modules so call sites stay stable
if the internal layout changes.

    from debatemind.cognee import remember_argument, recall_weaknesses
"""

from debatemind.cognee.fingerprint import (
    improve_fingerprint,
    remember_argument,
    remember_personal_fact,
    remember_session_summary,
)
from debatemind.cognee.forget import forget_pattern, forget_personal_fact
from debatemind.cognee.recall import recall_topic_weaknesses, recall_user_facts, recall_weaknesses

__all__ = [
    "remember_argument",
    "remember_session_summary",
    "remember_personal_fact",
    "recall_weaknesses",
    "recall_topic_weaknesses",
    "recall_user_facts",
    "improve_fingerprint",
    "forget_pattern",
    "forget_personal_fact",
]
```

- [ ] **Step 3: Update `mastery_svc.reactivate_pattern`**

In `debatemind-backend/debatemind/services/mastery_svc.py`, change:

```python
from debatemind.agents.mastery import MASTERY_THRESHOLD
from debatemind.cognee import reactivate_pattern_fact
from debatemind.models.mastery import MasteryLog
```

to:

```python
from debatemind.agents.mastery import MASTERY_THRESHOLD
from debatemind.models.mastery import MasteryLog
```

and change:

```python
    row = result.scalar_one_or_none()
    if row is None:
        return False

    await reactivate_pattern_fact(user_id, pattern_type)
    row.reactivated_at = datetime.now(timezone.utc)
    await db.commit()
    return True
```

to:

```python
    row = result.scalar_one_or_none()
    if row is None:
        return False

    # Only clears the Postgres gate so the opponent resumes targeting this
    # pattern — forget_pattern() already permanently deleted its ArgumentRecord
    # evidence from Cognee, and reactivation does not restore it. New evidence
    # accumulates fresh from here.
    row.reactivated_at = datetime.now(timezone.utc)
    await db.commit()
    return True
```

- [ ] **Step 4: Remove obsolete tests from `test_cognee_svc.py`**

In `debatemind-backend/tests/test_cognee_svc.py`, remove these test functions (their coverage now lives in `tests/test_cognee_recall.py` and `tests/test_cognee_forget.py`): `test_recall_weaknesses_searches_and_wraps_results_as_text_dicts`, `test_recall_weaknesses_excludes_mastered_patterns`, `test_forget_pattern_records_a_mastered_marker`, `test_reactivate_pattern_fact_records_a_reactivated_marker`.

Update the module's import block — change:

```python
from debatemind.cognee import _base
from debatemind.cognee import fingerprint as fingerprint_mod
from debatemind.cognee.fingerprint import (
    forget_pattern,
    improve_fingerprint,
    reactivate_pattern_fact,
    recall_weaknesses,
    remember_argument,
    remember_session_summary,
)
```

to:

```python
from debatemind.cognee import _base
from debatemind.cognee import fingerprint as fingerprint_mod
from debatemind.cognee.fingerprint import (
    improve_fingerprint,
    remember_argument,
    remember_session_summary,
)
```

- [ ] **Step 5: Update `test_mastery_svc.py`**

In `debatemind-backend/tests/test_mastery_svc.py`, change `test_reactivate_pattern_sets_reactivated_at` from:

```python
async def test_reactivate_pattern_sets_reactivated_at(db_session, monkeypatch):
    mock_reactivate = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "debatemind.services.mastery_svc.reactivate_pattern_fact",
        mock_reactivate,
    )
    db_session.add(MasteryLog(user_id="u1", pattern_type="StrawMan", rounds_to_mastery=3))
    await db_session.commit()

    ok = await reactivate_pattern(db_session, "u1", "StrawMan")

    assert ok is True
    row = (await db_session.execute(select(MasteryLog))).scalar_one()
    assert row.reactivated_at is not None
    mock_reactivate.assert_called_once_with("u1", "StrawMan")
```

to:

```python
async def test_reactivate_pattern_sets_reactivated_at(db_session):
    db_session.add(MasteryLog(user_id="u1", pattern_type="StrawMan", rounds_to_mastery=3))
    await db_session.commit()

    ok = await reactivate_pattern(db_session, "u1", "StrawMan")

    assert ok is True
    row = (await db_session.execute(select(MasteryLog))).scalar_one()
    assert row.reactivated_at is not None
```

The `from unittest.mock import AsyncMock` import at the top of the file is now unused — remove it.

- [ ] **Step 6: Run the full backend test suite**

Run: `cd debatemind-backend && .venv/bin/python -m pytest tests/ -v`
Expected: PASS, no failures, no `ModuleNotFoundError`/`ImportError`. In particular: `tests/test_cognee_svc.py`, `tests/test_mastery_svc.py`, `tests/test_pipeline_mastery_prune.py` (unaffected — it mocks `pipeline.forget_pattern` at the pipeline boundary, whose import now resolves via `debatemind.cognee.__init__` re-export, unchanged call site), `tests/test_cognee_schema.py`, `tests/test_cognee_base.py`, `tests/test_cognee_recall.py`, `tests/test_cognee_forget.py`.

- [ ] **Step 7: Run ruff to catch unused imports**

Run: `cd debatemind-backend && .venv/bin/ruff check debatemind/ tests/`
Expected: no errors (fix any unused-import findings the deletions above may have left behind, then re-run).

- [ ] **Step 8: Commit**

```bash
cd debatemind-backend
git add debatemind/cognee/fingerprint.py debatemind/cognee/__init__.py debatemind/services/mastery_svc.py tests/test_cognee_svc.py tests/test_mastery_svc.py
git commit -m "refactor: remove prose-marker recall/forget/reactivate, superseded by typed graph+vector join"
```

---

### Task 7: `graph_view.py` — read the raw graph, scoped to one user

**Files:**
- Create: `debatemind-backend/debatemind/cognee/graph_view.py`
- Test: `debatemind-backend/tests/test_cognee_graph_view.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (reads `get_graph_engine()` directly, like `recall.owned_nodes`, but needs edges too so doesn't reuse it).
- Produces: `user_graph_view(user_id: str, limit: int = 400) -> dict` returning `{"nodes": [{"id", "label", "type", "props"}], "edges": [{"source", "target", "label"}]}` (or `{"nodes": [], "edges": [], "error": "..."}` on failure). Consumed by the router in Task 8.

- [ ] **Step 1: Write the failing test file**

```python
# debatemind-backend/tests/test_cognee_graph_view.py
"""
Unit tests for debatemind.cognee.graph_view.user_graph_view — the ownership +
one-hop-adjacency filter that scopes the global Cognee graph to one user for
the knowledge-graph explorer panel. get_graph_engine() is mocked.
"""

from unittest.mock import AsyncMock, patch

from debatemind.cognee.graph_view import user_graph_view


class _FakeGraphEngine:
    def __init__(self, nodes, edges):
        self._nodes = nodes
        self._edges = edges

    async def get_graph_data(self):
        return self._nodes, self._edges


def _patched(nodes, edges):
    return patch(
        "cognee.infrastructure.databases.graph.get_graph_engine",
        new=AsyncMock(return_value=_FakeGraphEngine(nodes, edges)),
    )


async def test_includes_owned_nodes():
    nodes = [("a", {"id": "a", "type": "ArgumentRecord", "user_id": "u1", "summary": "s"})]
    with _patched(nodes, []):
        result = await user_graph_view("u1")

    assert [n["id"] for n in result["nodes"]] == ["a"]
    assert result["nodes"][0]["type"] == "ArgumentRecord"
    assert result["nodes"][0]["label"] == "s"


async def test_excludes_other_users_unconnected_nodes():
    nodes = [
        ("a", {"id": "a", "type": "ArgumentRecord", "user_id": "u1", "summary": "mine"}),
        ("b", {"id": "b", "type": "ArgumentRecord", "user_id": "u2", "summary": "not mine"}),
    ]
    with _patched(nodes, []):
        result = await user_graph_view("u1")

    assert [n["id"] for n in result["nodes"]] == ["a"]


async def test_includes_cognify_derived_entity_one_hop_from_owned_node():
    nodes = [
        ("a", {"id": "a", "type": "ArgumentRecord", "user_id": "u1", "summary": "mine"}),
        ("e", {"id": "e", "type": "Entity", "name": "SlipperySlope"}),  # no user_id
    ]
    edges = [("a", "e", "mentions")]
    with _patched(nodes, edges):
        result = await user_graph_view("u1")

    ids = {n["id"] for n in result["nodes"]}
    assert ids == {"a", "e"}
    entity = next(n for n in result["nodes"] if n["id"] == "e")
    assert entity["type"] == "Node"  # untyped/cognify-derived, not one of our schema classes
    assert entity["label"] == "SlipperySlope"


async def test_excludes_entities_not_connected_to_any_owned_node():
    nodes = [
        ("a", {"id": "a", "type": "ArgumentRecord", "user_id": "u1", "summary": "mine"}),
        ("f", {"id": "f", "type": "Entity", "name": "unrelated"}),
    ]
    with _patched(nodes, []):
        result = await user_graph_view("u1")

    assert {n["id"] for n in result["nodes"]} == {"a"}


async def test_edges_only_included_when_both_endpoints_present():
    nodes = [
        ("a", {"id": "a", "type": "ArgumentRecord", "user_id": "u1", "summary": "mine"}),
        ("b", {"id": "b", "type": "ArgumentRecord", "user_id": "u2", "summary": "not mine"}),
    ]
    edges = [("a", "b", "unrelated_edge")]
    with _patched(nodes, edges):
        result = await user_graph_view("u1")

    # b is not owned and not reachable from an owned node via any OTHER edge,
    # but this edge itself makes b adjacent to a — so b is included, and the
    # edge is included too (adjacency inheritance is intentionally one-hop-open).
    assert {n["id"] for n in result["nodes"]} == {"a", "b"}
    assert result["edges"] == [{"source": "a", "target": "b", "label": "unrelated_edge"}]


async def test_returns_empty_on_graph_engine_failure():
    with patch(
        "cognee.infrastructure.databases.graph.get_graph_engine",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        result = await user_graph_view("u1")

    assert result["nodes"] == []
    assert result["edges"] == []
    assert "error" in result


async def test_drops_embedding_property_from_output():
    nodes = [
        (
            "a",
            {
                "id": "a",
                "type": "ArgumentRecord",
                "user_id": "u1",
                "summary": "mine",
                "embedding": [0.1, 0.2],
            },
        )
    ]
    with _patched(nodes, []):
        result = await user_graph_view("u1")

    assert "embedding" not in result["nodes"][0]["props"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd debatemind-backend && .venv/bin/python -m pytest tests/test_cognee_graph_view.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'debatemind.cognee.graph_view'`

- [ ] **Step 3: Write `graph_view.py`**

```python
# debatemind-backend/debatemind/cognee/graph_view.py
"""Read-only view over Cognee's raw graph, scoped to one user, for the
knowledge-graph explorer panel (GET /api/users/me/knowledge-graph).

Distinct from debatemind/services/graph_svc.py, which derives a small,
mastery-colored fingerprint/brain graph from Postgres and powers the existing
gameplay UI (FingerprintGraph.tsx / BrainGraph.tsx) — this module instead
renders Cognee's actual entity graph: the typed nodes debatemind/cognee/schema.py
declares, plus whatever the cognify() LLM pass linked them to.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_LABEL_FIELDS = ("summary", "name", "fact_text", "claim_text", "user_id")
_TYPED_TYPES = {"UserProfile", "Topic", "ArgumentRecord", "SessionSummary", "PersonalFact"}


def _node_props(entry: Any) -> tuple[str, dict]:
    if isinstance(entry, tuple):
        nid, props = entry[0], entry[1]
    else:
        props, nid = entry, entry.get("id")
    return str(nid), dict(props or {})


def _edge_parts(entry: Any) -> tuple[str, str, str]:
    if isinstance(entry, tuple):
        src = str(entry[0]) if len(entry) > 0 else ""
        tgt = str(entry[1]) if len(entry) > 1 else ""
        label = str(entry[2]) if len(entry) > 2 else ""
        return src, tgt, label
    if isinstance(entry, dict):
        return (
            str(entry.get("source", "")),
            str(entry.get("target", "")),
            str(entry.get("label", "")),
        )
    return "", "", ""


def _label(node_type: str, props: dict) -> str:
    for field in _LABEL_FIELDS:
        val = props.get(field)
        if val:
            text = str(val)
            return text if len(text) <= 60 else text[:57] + "…"
    return node_type


def _safe_props(props: dict) -> dict:
    return {k: v for k, v in props.items() if k != "embedding"}


async def user_graph_view(user_id: str, limit: int = 400) -> dict:
    """{nodes, edges} for this user: owned typed nodes, plus any node one edge
    hop away from one of them (covers cognify-derived generic entities, which
    carry no `user_id` property of their own)."""
    from cognee.infrastructure.databases.graph import get_graph_engine

    try:
        engine = await get_graph_engine()
        raw_nodes, raw_edges = await engine.get_graph_data()
    except Exception:
        logger.exception("get_graph_data failed for user %s", user_id)
        return {"nodes": [], "edges": [], "error": "graph unavailable"}

    all_nodes: dict[str, dict] = {}
    for entry in raw_nodes:
        nid, props = _node_props(entry)
        all_nodes[nid] = props

    owned_ids = {nid for nid, props in all_nodes.items() if props.get("user_id") == user_id}

    edges = [_edge_parts(e) for e in raw_edges]
    adjacent_ids: set[str] = set()
    for src, tgt, _lbl in edges:
        if src in owned_ids:
            adjacent_ids.add(tgt)
        if tgt in owned_ids:
            adjacent_ids.add(src)

    included_ids = (owned_ids | adjacent_ids) & set(all_nodes.keys())

    nodes_out = []
    for nid in list(included_ids)[:limit]:
        props = all_nodes[nid]
        node_type = str(props.get("type") or "Node")
        nodes_out.append(
            {
                "id": nid,
                "label": _label(node_type, props),
                "type": node_type if node_type in _TYPED_TYPES else "Node",
                "props": _safe_props(props),
            }
        )

    included_set = {n["id"] for n in nodes_out}
    edges_out = [
        {"source": src, "target": tgt, "label": lbl}
        for src, tgt, lbl in edges
        if src in included_set and tgt in included_set
    ]

    return {"nodes": nodes_out, "edges": edges_out}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd debatemind-backend && .venv/bin/python -m pytest tests/test_cognee_graph_view.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
cd debatemind-backend
git add debatemind/cognee/graph_view.py tests/test_cognee_graph_view.py
git commit -m "feat: add user-scoped Cognee graph-view read path"
```

---

### Task 8: Router endpoints — `GET /me/knowledge-graph`, `DELETE /me/facts/{node_id}`

**Files:**
- Create: `debatemind-backend/debatemind/schemas/knowledge_graph.py`
- Modify: `debatemind-backend/debatemind/routers/users.py`
- Create: `debatemind-backend/tests/test_users_router.py`

**Interfaces:**
- Consumes: `debatemind.cognee.graph_view.user_graph_view` (Task 7), `debatemind.cognee.forget_personal_fact` (Task 5, re-exported via `debatemind.cognee.__init__` from Task 6).
- Produces: `KnowledgeGraphNode`, `KnowledgeGraphEdge`, `KnowledgeGraphOut` pydantic schemas; two new routes under `/api/users`.

- [ ] **Step 1: Write the failing router test file**

```python
# debatemind-backend/tests/test_users_router.py
"""
Router tests for the knowledge-graph endpoints — GET /me/knowledge-graph and
DELETE /me/facts/{node_id}. user_graph_view/forget_personal_fact are mocked;
no real Cognee calls happen here. Follows the FastAPI TestClient + dependency
override pattern used by tests/test_topics_router.py.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from debatemind.deps import current_user_id
from debatemind.routers import users as users_router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(users_router.router, prefix="/api/users")
    app.dependency_overrides[current_user_id] = lambda: "u1"
    return TestClient(app)


def test_get_knowledge_graph_returns_nodes_and_edges(client):
    view = {
        "nodes": [{"id": "a", "label": "mine", "type": "ArgumentRecord", "props": {}}],
        "edges": [],
    }
    with patch.object(users_router, "user_graph_view", new=AsyncMock(return_value=view)):
        res = client.get("/api/users/me/knowledge-graph")

    assert res.status_code == 200
    data = res.json()["data"]
    assert data["nodes"] == view["nodes"]
    assert data["edges"] == []


def test_delete_fact_returns_forgotten_status(client):
    with patch.object(
        users_router,
        "forget_personal_fact",
        new=AsyncMock(return_value={"node_id": "id-a", "status": "forgotten"}),
    ):
        res = client.delete("/api/users/me/facts/id-a")

    assert res.status_code == 200
    assert res.json()["data"] == {"node_id": "id-a", "status": "forgotten"}


def test_delete_fact_returns_404_when_not_found(client):
    with patch.object(
        users_router,
        "forget_personal_fact",
        new=AsyncMock(return_value={"node_id": "id-a", "status": "not_found"}),
    ):
        res = client.delete("/api/users/me/facts/id-a")

    assert res.status_code == 404
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd debatemind-backend && .venv/bin/python -m pytest tests/test_users_router.py -v`
Expected: FAIL — `AttributeError: module 'debatemind.routers.users' has no attribute 'user_graph_view'` (route/imports don't exist yet)

- [ ] **Step 3: Add the response schema**

```python
# debatemind-backend/debatemind/schemas/knowledge_graph.py
from typing import Any

from pydantic import BaseModel


class KnowledgeGraphNode(BaseModel):
    id: str
    label: str
    type: str
    props: dict[str, Any]


class KnowledgeGraphEdge(BaseModel):
    source: str
    target: str
    label: str


class KnowledgeGraphOut(BaseModel):
    nodes: list[KnowledgeGraphNode]
    edges: list[KnowledgeGraphEdge]
```

- [ ] **Step 4: Add the router endpoints**

In `debatemind-backend/debatemind/routers/users.py`, add to the imports:

```python
from debatemind.cognee import forget_personal_fact
from debatemind.cognee.graph_view import user_graph_view
from debatemind.schemas.knowledge_graph import KnowledgeGraphOut
```

Then, after the existing `get_brain_graph` endpoint (right before the `# ── ` section or the next `@router.get("/me/progress"...)` block — insert directly after the `get_brain_graph` function's closing `return SuccessResponse(data=GraphOut(nodes=nodes, edges=edges))`), add:

```python
@router.get(
    "/me/knowledge-graph",
    response_model=SuccessResponse[KnowledgeGraphOut],
    summary="Get raw Cognee knowledge graph",
    description=(
        "Retrieve the user's typed Cognee graph (arguments, topics, personal facts, "
        "session summaries) plus any entities cognify's LLM pass linked to them — "
        "distinct from /me/brain, which is a Postgres-derived, mastery-colored view."
    ),
    responses={401: {"model": UnauthorizedError, "description": "Invalid or missing token"}},
)
async def get_knowledge_graph(user_id: str = Depends(current_user_id)):
    view = await user_graph_view(user_id)
    return SuccessResponse(data=KnowledgeGraphOut(nodes=view["nodes"], edges=view["edges"]))


class ForgetFactOut(BaseModel):
    node_id: str
    status: str


@router.delete(
    "/me/facts/{node_id}",
    response_model=SuccessResponse[ForgetFactOut],
    summary="Forget a personal fact",
    description=(
        "Permanently delete one personal fact the user shared, from both the "
        "graph and its embedding."
    ),
    responses={
        401: {"model": UnauthorizedError, "description": "Invalid or missing token"},
        404: {"model": NotFoundError, "description": "Fact not found"},
    },
)
async def delete_fact(node_id: str, user_id: str = Depends(current_user_id)):
    result = await forget_personal_fact(user_id, node_id)
    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail="Fact not found")
    return SuccessResponse(data=ForgetFactOut(**result))
```

`HTTPException`, `NotFoundError`, `BaseModel` are already imported at the top of `users.py` (`from fastapi import APIRouter, Depends, HTTPException`, `from pydantic import BaseModel`, and `NotFoundError` needs adding to the existing `from debatemind.types import ...` import line — change it from `from debatemind.types import NotFoundError, SuccessResponse, UnauthorizedError` if not already present; check the current import line and add `NotFoundError` if missing).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd debatemind-backend && .venv/bin/python -m pytest tests/test_users_router.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Run the full backend test suite once more**

Run: `cd debatemind-backend && .venv/bin/python -m pytest tests/ -v`
Expected: PASS, no regressions.

- [ ] **Step 7: Commit**

```bash
cd debatemind-backend
git add debatemind/schemas/knowledge_graph.py debatemind/routers/users.py tests/test_users_router.py
git commit -m "feat: add GET /me/knowledge-graph and DELETE /me/facts/{node_id} endpoints"
```

---

### Task 9: Frontend types + API client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/api.ts`

**Interfaces:**
- Produces: `KnowledgeGraphNode { id, label, type, props: Record<string, unknown> }`, `KnowledgeGraphEdge { source, target, label }`, `KnowledgeGraphData { nodes: KnowledgeGraphNode[], edges: KnowledgeGraphEdge[] }`; `api.getKnowledgeGraph(): Promise<KnowledgeGraphData>`, `api.forgetFact(nodeId: string): Promise<{node_id: string, status: string}>`. Consumed by Task 10's `KnowledgeGraphView.tsx`.

- [ ] **Step 1: Add the types**

In `frontend/src/types/index.ts`, right after the existing `GraphData` interface (after line 34, the closing `}` of `GraphData`), add:

```typescript
export interface KnowledgeGraphNode {
  id: string;
  label: string;
  type: string;
  props: Record<string, unknown>;
}

export interface KnowledgeGraphEdge {
  source: string;
  target: string;
  label: string;
}

export interface KnowledgeGraphData {
  nodes: KnowledgeGraphNode[];
  edges: KnowledgeGraphEdge[];
}
```

- [ ] **Step 2: Add the API client methods**

In `frontend/src/lib/api.ts`, right after the existing `getBrainGraph` line:

```typescript
  getBrainGraph: () => apiFetch<{ nodes: import("@/types").GraphNode[]; edges: import("@/types").GraphEdge[] }>("/api/users/me/brain"),
```

add:

```typescript
  getKnowledgeGraph: () => apiFetch<import("@/types").KnowledgeGraphData>("/api/users/me/knowledge-graph"),
  forgetFact: (nodeId: string) =>
    apiFetch<{ node_id: string; status: string }>(`/api/users/me/facts/${nodeId}`, { method: "DELETE" }),
```

- [ ] **Step 3: Verify the frontend still builds**

Run: `cd frontend && npm run build`
Expected: build succeeds with no TypeScript errors.

- [ ] **Step 4: Commit**

```bash
cd frontend
git add src/types/index.ts src/lib/api.ts
git commit -m "feat: add knowledge-graph types and API client methods"
```

---

### Task 10: `KnowledgeGraphView.tsx` component

**Files:**
- Create: `frontend/src/components/graph/KnowledgeGraphView.tsx`

**Interfaces:**
- Consumes: `KnowledgeGraphData`, `KnowledgeGraphNode`, `KnowledgeGraphEdge` (Task 9).
- Produces: `export default function KnowledgeGraphView({ data }: { data: KnowledgeGraphData })` — d3 force graph. Consumed by Task 11.

- [ ] **Step 1: Write the component**

```tsx
// frontend/src/components/graph/KnowledgeGraphView.tsx
"use client";
import { useEffect, useRef } from "react";
import * as d3 from "d3";
import { KnowledgeGraphData, KnowledgeGraphNode } from "@/types";

// Distinct vocabulary from BrainGraph's weakness/strength/mastered/topic —
// this renders Cognee's raw typed graph, not the Postgres-derived mastery view.
const NODE_COLOR: Record<string, string> = {
  UserProfile: "#0d0d0d",
  Topic: "#1e3a5f",
  ArgumentRecord: "#C0392B",
  SessionSummary: "#8e44ad",
  PersonalFact: "#27AE60",
  Node: "#555",
};

const NODE_R: Record<string, number> = {
  UserProfile: 26,
  Topic: 18,
  ArgumentRecord: 11,
  SessionSummary: 13,
  PersonalFact: 11,
  Node: 8,
};

type SimNode = KnowledgeGraphNode & d3.SimulationNodeDatum;
type SimLink = { source: string; target: string; label: string } & d3.SimulationLinkDatum<SimNode>;

export default function KnowledgeGraphView({ data }: { data: KnowledgeGraphData }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;

    const W = svg.clientWidth || 600;
    const H = svg.clientHeight || 500;

    const nodes: SimNode[] = data.nodes.map((n) => ({ ...n }));
    const links: SimLink[] = data.edges.map((e) => ({ ...e }));

    const sel = d3.select(svg);
    sel.selectAll("*").remove();

    const g = sel.append("g");
    sel.call(
      d3.zoom<SVGSVGElement, unknown>()
        .scaleExtent([0.3, 3])
        .on("zoom", (ev) => g.attr("transform", ev.transform))
    );

    const link = g
      .append("g")
      .selectAll<SVGLineElement, SimLink>("line")
      .data(links)
      .join("line")
      .attr("stroke", "rgba(255,255,255,0.15)")
      .attr("stroke-width", 1);

    const node = g
      .append("g")
      .selectAll<SVGGElement, SimNode>("g")
      .data(nodes)
      .join("g")
      .attr("cursor", "grab");

    node.call(
      d3.drag<SVGGElement, SimNode>()
        .on("start", (ev, d) => {
          if (!ev.active) sim.alphaTarget(0.3).restart();
          d.fx = d.x;
          d.fy = d.y;
        })
        .on("drag", (ev, d) => {
          d.fx = ev.x;
          d.fy = ev.y;
        })
        .on("end", (ev, d) => {
          if (!ev.active) sim.alphaTarget(0);
          d.fx = null;
          d.fy = null;
        })
    );

    node
      .append("circle")
      .attr("r", (d) => NODE_R[d.type] ?? 10)
      .attr("fill", (d) => NODE_COLOR[d.type] ?? "#555")
      .attr("stroke", "rgba(255,255,255,0.2)")
      .attr("stroke-width", 1);

    const tt = tooltipRef.current;
    node
      .on("mouseenter", (ev, d) => {
        if (!tt) return;
        tt.textContent = `${d.label} (${d.type})`;
        tt.style.opacity = "1";
        tt.style.left = ev.pageX + 14 + "px";
        tt.style.top = ev.pageY - 10 + "px";
      })
      .on("mousemove", (ev) => {
        if (!tt) return;
        tt.style.left = ev.pageX + 14 + "px";
        tt.style.top = ev.pageY - 10 + "px";
      })
      .on("mouseleave", () => {
        if (tt) tt.style.opacity = "0";
      });

    const sim = d3
      .forceSimulation<SimNode>(nodes)
      .force(
        "link",
        d3
          .forceLink<SimNode, SimLink>(links)
          .id((d) => d.id)
          .distance(70)
      )
      .force("charge", d3.forceManyBody<SimNode>().strength(-120))
      .force("center", d3.forceCenter(W / 2, H / 2))
      .force(
        "collision",
        d3.forceCollide<SimNode>((d) => (NODE_R[d.type] ?? 10) + 4)
      );

    sim.on("tick", () => {
      link
        .attr("x1", (d) => (d.source as unknown as SimNode).x ?? 0)
        .attr("y1", (d) => (d.source as unknown as SimNode).y ?? 0)
        .attr("x2", (d) => (d.target as unknown as SimNode).x ?? 0)
        .attr("y2", (d) => (d.target as unknown as SimNode).y ?? 0);
      node.attr("transform", (d) => `translate(${d.x ?? 0},${d.y ?? 0})`);
    });

    return () => {
      sim.stop();
    };
  }, [data]);

  if (!data.nodes.length) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-3 p-8">
        <span className="text-4xl opacity-20">🕸️</span>
        <p className="font-sans text-[12px] text-white/30 text-center leading-relaxed">
          No knowledge graph yet.
          <br />
          Start debating to grow it.
        </p>
      </div>
    );
  }

  return (
    <div className="relative flex-1 w-full h-full">
      <svg ref={svgRef} width="100%" height="100%" style={{ display: "block" }} />
      <div
        ref={tooltipRef}
        className="fixed z-[200] pointer-events-none px-2.5 py-1.5 rounded-md bg-[#1c1c1c] border border-white/15 font-sans text-[11px] text-white/80 shadow-lg transition-opacity duration-100"
        style={{ opacity: 0 }}
      />
    </div>
  );
}
```

- [ ] **Step 2: Verify the frontend still builds**

Run: `cd frontend && npm run build`
Expected: build succeeds with no TypeScript errors.

- [ ] **Step 3: Commit**

```bash
cd frontend
git add src/components/graph/KnowledgeGraphView.tsx
git commit -m "feat: add KnowledgeGraphView component for the raw Cognee graph"
```

---

### Task 11: Wire a tab switcher into `BrainMapModal`

**Files:**
- Modify: `frontend/src/components/sidebar/SessionSidebar.tsx`

**Interfaces:**
- Consumes: `KnowledgeGraphView` (Task 10), `api.getKnowledgeGraph()` (Task 9).
- Produces: no new exports — `BrainMapModal` gains an internal tab switcher; its existing props (`onClose`, `winRate`, `totalSessions`, `description`) are unchanged, so its one call site (line 532) needs no changes.

- [ ] **Step 1: Add the import**

In `frontend/src/components/sidebar/SessionSidebar.tsx`, change:

```typescript
import BrainGraph from "@/components/graph/BrainGraph";
```

to:

```typescript
import BrainGraph from "@/components/graph/BrainGraph";
import KnowledgeGraphView from "@/components/graph/KnowledgeGraphView";
```

Also add `IconNetwork` if not already imported for the tab icon — it already is (line 12 of the existing import list).

- [ ] **Step 2: Add tab state and a second fetch inside `BrainMapModal`**

Change the top of `BrainMapModal` from:

```typescript
function BrainMapModal({
  onClose,
  winRate,
  totalSessions,
  description,
}: {
  onClose: () => void;
  winRate: number | null;
  totalSessions: number;
  description: string | null;
}) {
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState(false);

  useEffect(() => {
    api.getBrainGraph()
      .then((d) => setGraphData(d))
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);
```

to:

```typescript
function BrainMapModal({
  onClose,
  winRate,
  totalSessions,
  description,
}: {
  onClose: () => void;
  winRate: number | null;
  totalSessions: number;
  description: string | null;
}) {
  const [tab, setTab] = useState<"brain" | "knowledge">("brain");

  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState(false);

  const [kgData, setKgData]       = useState<KnowledgeGraphData | null>(null);
  const [kgLoading, setKgLoading] = useState(false);
  const [kgError, setKgError]     = useState(false);

  useEffect(() => {
    api.getBrainGraph()
      .then((d) => setGraphData(d))
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (tab !== "knowledge" || kgData || kgLoading) return;
    setKgLoading(true);
    api.getKnowledgeGraph()
      .then((d) => setKgData(d))
      .catch(() => setKgError(true))
      .finally(() => setKgLoading(false));
  }, [tab, kgData, kgLoading]);
```

Add `KnowledgeGraphData` to the existing type import at the top of the file — change:

```typescript
import { GraphData, SessionListItem } from "@/types";
```

to:

```typescript
import { GraphData, KnowledgeGraphData, SessionListItem } from "@/types";
```

- [ ] **Step 3: Add the tab switcher UI and conditionally render each panel**

Change the header's legend block from:

```tsx
        <div className="flex items-center gap-5">
          {LEGEND.map((l) => (
            <div key={l.label} className="flex items-center gap-1.5">
              <span
                className="inline-block w-3 h-3 rounded-full border"
                style={{ background: l.color, borderColor: l.border }}
              />
              <span className="font-sans text-[12px] text-fog">{l.label}</span>
            </div>
          ))}
        </div>
```

to:

```tsx
        <div className="flex items-center gap-5">
          <div className="flex items-center gap-1 bg-fog/5 rounded-md p-0.5">
            <button
              onClick={() => setTab("brain")}
              className={`px-2.5 py-1 rounded font-sans text-[11px] transition-colors ${
                tab === "brain" ? "bg-white text-ink shadow-sm" : "text-fog"
              }`}
            >
              Brain Map
            </button>
            <button
              onClick={() => setTab("knowledge")}
              className={`px-2.5 py-1 rounded font-sans text-[11px] transition-colors ${
                tab === "knowledge" ? "bg-white text-ink shadow-sm" : "text-fog"
              }`}
            >
              Knowledge Graph
            </button>
          </div>
          {tab === "brain" &&
            LEGEND.map((l) => (
              <div key={l.label} className="flex items-center gap-1.5">
                <span
                  className="inline-block w-3 h-3 rounded-full border"
                  style={{ background: l.color, borderColor: l.border }}
                />
                <span className="font-sans text-[12px] text-fog">{l.label}</span>
              </div>
            ))}
        </div>
```

Then change the graph panel body from:

```tsx
        <div className="flex-1 relative overflow-hidden bg-[#0d0d0d]">
          {loading && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="flex flex-col items-center gap-3">
                <span className="text-4xl opacity-30 animate-pulse">🧠</span>
                <p className="font-sans text-[13px] text-white/30">Building your brain map…</p>
              </div>
            </div>
          )}
          {error && (
            <div className="absolute inset-0 flex items-center justify-center">
              <p className="font-sans text-[13px] text-white/30">Failed to load brain map.</p>
            </div>
          )}
          {graphData && !loading && <BrainGraph data={graphData} />}
          <div className="absolute bottom-3 left-0 right-0 flex justify-center pointer-events-none">
            <span className="font-sans text-[10px] text-white/20">
              Scroll to zoom · drag nodes · click topic to expand
            </span>
          </div>
        </div>
```

to:

```tsx
        <div className="flex-1 relative overflow-hidden bg-[#0d0d0d]">
          {tab === "brain" && (
            <>
              {loading && (
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="flex flex-col items-center gap-3">
                    <span className="text-4xl opacity-30 animate-pulse">🧠</span>
                    <p className="font-sans text-[13px] text-white/30">Building your brain map…</p>
                  </div>
                </div>
              )}
              {error && (
                <div className="absolute inset-0 flex items-center justify-center">
                  <p className="font-sans text-[13px] text-white/30">Failed to load brain map.</p>
                </div>
              )}
              {graphData && !loading && <BrainGraph data={graphData} />}
              <div className="absolute bottom-3 left-0 right-0 flex justify-center pointer-events-none">
                <span className="font-sans text-[10px] text-white/20">
                  Scroll to zoom · drag nodes · click topic to expand
                </span>
              </div>
            </>
          )}
          {tab === "knowledge" && (
            <>
              {kgLoading && (
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="flex flex-col items-center gap-3">
                    <span className="text-4xl opacity-30 animate-pulse">🕸️</span>
                    <p className="font-sans text-[13px] text-white/30">Loading knowledge graph…</p>
                  </div>
                </div>
              )}
              {kgError && (
                <div className="absolute inset-0 flex items-center justify-center">
                  <p className="font-sans text-[13px] text-white/30">Failed to load knowledge graph.</p>
                </div>
              )}
              {kgData && !kgLoading && <KnowledgeGraphView data={kgData} />}
              <div className="absolute bottom-3 left-0 right-0 flex justify-center pointer-events-none">
                <span className="font-sans text-[10px] text-white/20">
                  Scroll to zoom · drag nodes — raw Cognee graph, unfiltered by mastery
                </span>
              </div>
            </>
          )}
        </div>
```

- [ ] **Step 4: Verify the frontend builds**

Run: `cd frontend && npm run build`
Expected: build succeeds with no TypeScript errors.

- [ ] **Step 5: Manual verification**

Run: `cd frontend && npm run dev` (and ensure the backend + docker-compose services — Postgres, Neo4j, Redis — are running per the project's `run.sh`/`docker-compose.yml`).

In the browser: log in, play a few debate turns (so `remember_argument` writes at least one `ArgumentRecord`), open the sidebar's Brain Map (the button using `IconBrain`/`IconNetwork` that opens `BrainMapModal`), confirm the "Brain Map" tab still renders as before, click "Knowledge Graph", confirm it fetches `GET /api/users/me/knowledge-graph` and renders at least a `UserProfile`, `Topic`, and `ArgumentRecord` node with an edge between them. Master a pattern (3 wins in a row, per `MASTERY_THRESHOLD`) and confirm its `ArgumentRecord` node(s) disappear from the Knowledge Graph tab on next load.

- [ ] **Step 6: Commit**

```bash
cd frontend
git add src/components/sidebar/SessionSidebar.tsx
git commit -m "feat: add Knowledge Graph tab to the Brain Map modal"
```
