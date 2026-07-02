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
