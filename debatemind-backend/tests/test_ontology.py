"""Tests for the Cognee debate-domain ontology asset and its resolver.

The ontology is a static, hand-authored OWL/RDF file committed inside the
package. It is a WIDE, generic model of how a person thinks — reasoning
approaches, argument patterns, fallacies, cognitive biases — plus an OPEN
knowledge-domain root (no hardcoded subject areas: concrete domains are created
dynamically per user by the extractor). These tests guard that the asset
exists, is well-formed, exposes the expected generic vocabulary, keeps the
extractor's controlled strings in sync (the accuracy linchpin), stays free of a
baked-in domain taxonomy, and that the resolver degrades gracefully when the
file is missing.
"""

import owlready2

from debatemind.agents.constants import PATTERN_TYPES
from debatemind.cognee import _base

# The extractor's evidence_quality enum (see agents/prompts/extractor.py). Kept
# here so a drift in either place fails loudly.
EVIDENCE_QUALITY_VALUES = {"Strong", "Moderate", "Weak", "Absent"}


def _load():
    return owlready2.get_ontology(_base.ontology_file()).load()


def _class_names(onto):
    return {c.name for c in onto.classes()}


def _individual_names(onto):
    return {i.name for i in onto.individuals()}


def test_ontology_file_returns_existing_path():
    path = _base.ontology_file()
    assert path is not None
    assert _base.ONTOLOGY_PATH.exists()
    assert path == str(_base.ONTOLOGY_PATH)
    assert path.endswith("debate_domain.owl")


def test_ontology_file_returns_none_when_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(_base, "ONTOLOGY_PATH", tmp_path / "does_not_exist.owl")
    assert _base.ontology_file() is None


def test_ontology_exposes_the_wide_class_taxonomy():
    names = _class_names(_load())
    expected = {
        # structure
        "Thinker",
        "Argument",
        "Session",
        "Topic",
        # cognitive dimension (how they think)
        "ThinkingStyle",
        "ReasoningApproach",
        "ArgumentPattern",
        "Fallacy",
        "CognitiveBias",
        # evidence
        "EvidenceQuality",
        "EvidenceType",
        # performance
        "Outcome",
        "MasteryStatus",
        "SkillLevel",
        # knowledge: an OPEN root only, no hardcoded subject areas
        "KnowledgeDomain",
    }
    assert expected.issubset(names)


def test_argument_pattern_individuals_match_the_extractor_enum():
    """Accuracy linchpin: every string the extractor can emit as pattern_type
    must be a named individual, else Cognee can't attach the user's data to a
    typed node. This test fails if constants.PATTERN_TYPES drifts."""
    names = _individual_names(_load())
    missing = set(PATTERN_TYPES) - names
    assert not missing, f"ArgumentPattern individuals missing from ontology: {missing}"


def test_voice_note_map_patterns_are_present():
    names = _individual_names(_load())
    for name in ("FallacyUsed", "PositionFlip", "StrongArgument"):
        assert name in names


def test_evidence_quality_individuals_match_the_extractor_enum():
    names = _individual_names(_load())
    assert EVIDENCE_QUALITY_VALUES.issubset(names)


def test_thinking_style_and_performance_individuals_present():
    names = _individual_names(_load())
    for name in ("Logic", "Evidence", "Rhetoric", "Won", "Lost", "Mastered", "Reactivated"):
        assert name in names


def test_reasoning_and_bias_individuals_present():
    names = _individual_names(_load())
    for name in ("Deductive", "Inductive", "Analogical", "ConfirmationBias"):
        assert name in names


def test_knowledge_domain_is_an_open_root_with_no_hardcoded_subjects():
    """Generic, test-oriented app: KnowledgeDomain must stay an OPEN root with
    NO committed subject-area subclasses. Concrete domains ("skills") are created
    dynamically per user by the extractor at runtime, hung off this root and off
    Topic. This guards against anyone re-introducing a fixed domain taxonomy
    (e.g. Technology / ArtificialIntelligence / Politics) into the ontology."""
    onto = _load()
    by_name = {c.name: c for c in onto.classes()}
    assert "KnowledgeDomain" in by_name

    domain_subclasses = [
        c.name
        for c in onto.classes()
        if by_name["KnowledgeDomain"] in c.is_a and c is not by_name["KnowledgeDomain"]
    ]
    assert not domain_subclasses, (
        "KnowledgeDomain must have no hardcoded subject subclasses — domains are "
        f"created dynamically per user. Found baked-in: {domain_subclasses}"
    )
