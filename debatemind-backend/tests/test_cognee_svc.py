"""
Unit tests for debatemind.cognee — verifies the service calls the real cognee SDK API
(add/cognify/search), not the nonexistent remember/recall/improve methods.
cognee.* calls are mocked; no real cognee storage/LLM calls happen here.
"""

from unittest.mock import AsyncMock

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


async def test_remember_argument_adds_then_cognifies_the_dataset(monkeypatch):
    call_order: list[str] = []

    async def track_add(*args, **kwargs):
        call_order.append("add")

    async def track_cognify(*args, **kwargs):
        call_order.append("cognify")

    add_mock = AsyncMock(side_effect=track_add)
    cognify_mock = AsyncMock(side_effect=track_cognify)
    monkeypatch.setattr(fingerprint_mod.cognee, "add", add_mock)
    monkeypatch.setattr(fingerprint_mod.cognee, "cognify", cognify_mock)

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

    add_mock.assert_awaited_once()
    text_arg, kwargs = add_mock.call_args.args[0], add_mock.call_args.kwargs
    assert kwargs["dataset_name"] == "user_u1_fingerprint"
    assert "AI will inevitably take over" in text_arg
    assert "SlipperySlope" in text_arg
    # Enrichment: the extractor's reasoning sentence is stored so cognify can
    # extract ReasoningApproach / EvidenceType / bias against the ontology.
    assert "Asserts an extreme outcome without a causal chain." in text_arg

    cognify_mock.assert_awaited_once_with(
        datasets="user_u1_fingerprint", ontology_file_path=_base.ontology_file()
    )
    assert call_order == ["add", "cognify"]


async def test_remember_argument_writes_natural_language_summary(monkeypatch):
    add_mock = AsyncMock()
    monkeypatch.setattr(fingerprint_mod.cognee, "add", add_mock)
    monkeypatch.setattr(fingerprint_mod.cognee, "cognify", AsyncMock())

    await remember_argument(
        user_id="u1",
        session_id="s1",
        topic="AI Safety",
        claim_text="AI will inevitably take over",
        pattern_type="SlipperySlope",
        fallacy="SlipperySlope",
        evidence_quality="Weak",
        outcome="Lost",
    )

    text_arg = add_mock.call_args.args[0]
    # A prose sentence (not just key:value markers) gives cognify's LLM extractor
    # material to link the topic to a KnowledgeDomain and type the argument.
    assert 'In a debate about "AI Safety"' in text_arg
    # Structured markers preserved — recall/isolation still depends on them.
    assert "User: u1" in text_arg
    assert "ArgumentPattern: SlipperySlope" in text_arg


async def test_remember_session_summary_writes_topic_prose(monkeypatch):
    add_mock = AsyncMock()
    monkeypatch.setattr(fingerprint_mod.cognee, "add", add_mock)
    monkeypatch.setattr(fingerprint_mod.cognee, "cognify", AsyncMock())

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

    text_arg = add_mock.call_args.args[0]
    assert "User: u1" in text_arg
    # Prose weaving topic (-> domain) + patterns + thinking style for extraction.
    assert 'debating "AI regulation"' in text_arg
    assert "the user won" in text_arg
    assert "SlipperySlope" in text_arg


async def test_recall_weaknesses_searches_and_wraps_results_as_text_dicts(monkeypatch):
    # Records must carry the "User: <id>" marker to survive the ownership filter.
    search_mock = AsyncMock(
        return_value=[
            "User: u1\nArgumentPattern: StrawMan\nOutcome: Lost",
            "User: u1\nArgumentPattern: AdHominem\nOutcome: Lost",
            "User: someone_else\nArgumentPattern: StrawMan",  # must be filtered out
        ]
    )
    monkeypatch.setattr(fingerprint_mod.cognee, "search", search_mock)

    results = await recall_weaknesses("u1")

    search_mock.assert_awaited_once()
    kwargs = search_mock.call_args.kwargs
    # Isolation-safe vector retrieval: CHUNKS + a per-user "User:" marker filter.
    # (Graph-native retrievers in cognee 0.1.40 traverse the GLOBAL graph and
    # would leak other users' patterns, so recall deliberately uses CHUNKS.)
    assert kwargs["query_type"] == fingerprint_mod.SearchType.CHUNKS
    assert kwargs["datasets"] == ["user_u1_fingerprint"]
    assert kwargs["top_k"] == 20

    # Only this user's records survive; the other user's record is dropped.
    assert results == [
        {"text": "User: u1\nArgumentPattern: StrawMan\nOutcome: Lost"},
        {"text": "User: u1\nArgumentPattern: AdHominem\nOutcome: Lost"},
    ]


async def test_recall_weaknesses_excludes_mastered_patterns(monkeypatch):
    search_mock = AsyncMock(
        return_value=[
            "User: u1\nArgumentPattern: StrawMan\nOutcome: Lost",
            "User: u1\nArgumentPattern: AdHominem\nOutcome: Lost",
        ]
    )
    monkeypatch.setattr(fingerprint_mod.cognee, "search", search_mock)

    # Once StrawMan is mastered, it must not be recalled as a weakness anymore.
    results = await recall_weaknesses("u1", exclude_patterns={"StrawMan"})

    assert results == [{"text": "User: u1\nArgumentPattern: AdHominem\nOutcome: Lost"}]


async def test_improve_fingerprint_recognifies_the_dataset(monkeypatch):
    cognify_mock = AsyncMock()
    monkeypatch.setattr(fingerprint_mod.cognee, "cognify", cognify_mock)

    await improve_fingerprint("u1")

    cognify_mock.assert_awaited_once_with(
        datasets="user_u1_fingerprint", ontology_file_path=_base.ontology_file()
    )


async def test_forget_pattern_records_a_mastered_marker(monkeypatch):
    add_mock = AsyncMock()
    cognify_mock = AsyncMock()
    monkeypatch.setattr(fingerprint_mod.cognee, "add", add_mock)
    monkeypatch.setattr(fingerprint_mod.cognee, "cognify", cognify_mock)

    await forget_pattern("u1", "StrawMan")

    add_mock.assert_awaited_once()
    text_arg, kwargs = add_mock.call_args.args[0], add_mock.call_args.kwargs
    assert kwargs["dataset_name"] == "user_u1_fingerprint"
    assert "MASTERED" in text_arg
    assert "StrawMan" in text_arg

    cognify_mock.assert_awaited_once_with(
        datasets="user_u1_fingerprint", ontology_file_path=_base.ontology_file()
    )


async def test_reactivate_pattern_fact_records_a_reactivated_marker(monkeypatch):
    add_mock = AsyncMock()
    cognify_mock = AsyncMock()
    monkeypatch.setattr(fingerprint_mod.cognee, "add", add_mock)
    monkeypatch.setattr(fingerprint_mod.cognee, "cognify", cognify_mock)

    await reactivate_pattern_fact("u1", "AdHominem")

    add_mock.assert_awaited_once()
    text_arg, kwargs = add_mock.call_args.args[0], add_mock.call_args.kwargs
    assert kwargs["dataset_name"] == "user_u1_fingerprint"
    assert "REACTIVATED" in text_arg
    assert "AdHominem" in text_arg

    cognify_mock.assert_awaited_once_with(
        datasets="user_u1_fingerprint", ontology_file_path=_base.ontology_file()
    )


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
