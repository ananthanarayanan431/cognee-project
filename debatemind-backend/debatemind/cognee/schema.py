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

from cognee.infrastructure.engine import DataPoint
from pydantic import SkipValidation

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
