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
