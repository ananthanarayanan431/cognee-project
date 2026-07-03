"""Shared constants, dataset-name builders, and log helpers for every cognee module."""

import re
import time
from pathlib import Path

ADD_TIMEOUT = 60.0
COGNIFY_TIMEOUT = 300.0
SEARCH_TIMEOUT = 10.0

# Static, hand-authored domain ontology that guides cognee's graph extraction.
# Resolved from this module's location (not the process CWD) so it works the
# same whether run from source, a wheel, or the Docker image.
ONTOLOGY_PATH = Path(__file__).parent / "ontology" / "debate_domain.owl"


def ontology_file() -> str | None:
    """Absolute path to the debate ontology, or None if the asset is absent.

    Returning None makes cognee.cognify() behave exactly as before (it falls
    back to an empty ontology), so a missing file degrades gracefully in
    production instead of raising.
    """
    return str(ONTOLOGY_PATH) if ONTOLOGY_PATH.exists() else None


def fingerprint_dataset(user_id: str) -> str:
    return f"user_{user_id}_fingerprint"


def elapsed_ms(t0: float) -> int:
    return int((time.monotonic() - t0) * 1000)


def preview(text: str, limit: int = 200) -> str:
    return text[:limit] + ("…" if len(text) > limit else "")


def result_text(r) -> str:
    if isinstance(r, str):
        return r
    if isinstance(r, dict):
        return r.get("text", str(r))
    return getattr(r, "text", str(r))


# --------------------------------------------------------------------------
# Ontology vocabulary — the controlled entity names cognify() links argument
# records to (see ontology/debate_domain.owl). recall.py walks one graph hop
# out from each owned ArgumentRecord and classifies neighbour entities against
# these sets to surface the cognitive signal (biases, reasoning style, evidence
# type) that lives ONLY in the LLM-derived graph, not on the record's own
# fields. Kept in sync with the .owl by tests/test_ontology.py — edit both.
FALLACIES: frozenset[str] = frozenset(
    {
        "AppealToAuthority",
        "StrawMan",
        "AdHominem",
        "SlipperySlope",
        "FalseEquivalence",
        "EmotionalAppeal",
        "HastyGeneralization",
        "FalseDichotomy",
        "CircularReasoning",
        "RedHerring",
        "Whataboutism",
    }
)
REASONING_APPROACHES: frozenset[str] = frozenset(
    {
        "Deductive",
        "Inductive",
        "Abductive",
        "Analogical",
        "Causal",
        "Probabilistic",
        "FirstPrinciples",
    }
)
COGNITIVE_BIASES: frozenset[str] = frozenset(
    {
        "ConfirmationBias",
        "AnchoringBias",
        "AvailabilityBias",
        "MotivatedReasoning",
        "Overconfidence",
    }
)
EVIDENCE_TYPES: frozenset[str] = frozenset(
    {
        "Empirical",
        "Statistical",
        "Anecdotal",
        "Testimonial",
        "Logical",
        "Historical",
    }
)


def _normalize_entity(name: str) -> str:
    """Fold cognify's fuzzy label ('Straw Man', 'straw-man') to a match key."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


# normalized entity name -> (category, canonical_name)
_ENTITY_LOOKUP: dict[str, tuple[str, str]] = {
    _normalize_entity(name): (category, name)
    for category, names in (
        ("fallacy", FALLACIES),
        ("reasoning", REASONING_APPROACHES),
        ("bias", COGNITIVE_BIASES),
        ("evidence_type", EVIDENCE_TYPES),
    )
    for name in names
}


def classify_entity(name: str | None) -> tuple[str, str] | None:
    """Classify a cognify-derived neighbour name into (category, canonical_name).

    Returns None for names that aren't part of the cognitive vocabulary (topic
    entities, the user's own typed nodes, free text) — those are ignored by the
    cognitive-profile aggregation rather than misfiled.
    """
    if not name:
        return None
    return _ENTITY_LOOKUP.get(_normalize_entity(name))


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
