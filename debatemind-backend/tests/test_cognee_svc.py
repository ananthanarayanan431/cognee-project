"""
Unit tests for cognee_svc — verifies the service calls the real cognee SDK API
(add/cognify/search), not the nonexistent remember/recall/improve methods.
cognee.* calls are mocked; no real cognee storage/LLM calls happen here.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from debatemind.services import cognee_svc


async def test_remember_argument_adds_then_cognifies_the_dataset(monkeypatch):
    add_mock = AsyncMock()
    cognify_mock = AsyncMock()
    monkeypatch.setattr(cognee_svc.cognee, "add", add_mock)
    monkeypatch.setattr(cognee_svc.cognee, "cognify", cognify_mock)

    await cognee_svc.remember_argument(
        user_id="u1",
        session_id="s1",
        topic="AI Safety",
        claim_text="AI will inevitably take over",
        pattern_type="SlipperySlope",
        fallacy="SlipperySlope",
        evidence_quality="Weak",
        outcome="Lost",
    )

    add_mock.assert_awaited_once()
    text_arg, kwargs = add_mock.call_args.args[0], add_mock.call_args.kwargs
    assert kwargs["dataset_name"] == "user_u1_fingerprint"
    assert "AI will inevitably take over" in text_arg
    assert "SlipperySlope" in text_arg

    cognify_mock.assert_awaited_once_with(datasets="user_u1_fingerprint")


async def test_recall_weaknesses_searches_and_wraps_results_as_text_dicts(monkeypatch):
    search_mock = AsyncMock(return_value=["StrawMan pattern found", "AdHominem pattern found"])
    monkeypatch.setattr(cognee_svc.cognee, "search", search_mock)

    results = await cognee_svc.recall_weaknesses("u1")

    search_mock.assert_awaited_once()
    kwargs = search_mock.call_args.kwargs
    assert kwargs["query_type"] == cognee_svc.SearchType.GRAPH_COMPLETION
    assert kwargs["datasets"] == ["user_u1_fingerprint"]
    assert kwargs["top_k"] == 10
    assert "u1" in kwargs["query_text"]

    assert results == [
        {"text": "StrawMan pattern found"},
        {"text": "AdHominem pattern found"},
    ]


async def test_improve_fingerprint_recognifies_the_dataset(monkeypatch):
    cognify_mock = AsyncMock()
    monkeypatch.setattr(cognee_svc.cognee, "cognify", cognify_mock)

    await cognee_svc.improve_fingerprint("u1", "s1")

    cognify_mock.assert_awaited_once_with(datasets="user_u1_fingerprint")


async def test_forget_pattern_records_a_mastered_marker(monkeypatch):
    add_mock = AsyncMock()
    cognify_mock = AsyncMock()
    monkeypatch.setattr(cognee_svc.cognee, "add", add_mock)
    monkeypatch.setattr(cognee_svc.cognee, "cognify", cognify_mock)

    await cognee_svc.forget_pattern("u1", "StrawMan")

    add_mock.assert_awaited_once()
    text_arg, kwargs = add_mock.call_args.args[0], add_mock.call_args.kwargs
    assert kwargs["dataset_name"] == "user_u1_fingerprint"
    assert "MASTERED" in text_arg
    assert "StrawMan" in text_arg

    cognify_mock.assert_awaited_once_with(datasets="user_u1_fingerprint")


async def test_index_source_document_adds_then_cognifies_the_session_dataset(monkeypatch):
    add_mock = AsyncMock()
    cognify_mock = AsyncMock()
    monkeypatch.setattr(cognee_svc.cognee, "add", add_mock)
    monkeypatch.setattr(cognee_svc.cognee, "cognify", cognify_mock)

    await cognee_svc.index_source_document("s1", "/tmp/evidence.pdf")

    add_mock.assert_awaited_once_with("/tmp/evidence.pdf", dataset_name="session_s1_source")
    cognify_mock.assert_awaited_once_with(datasets="session_s1_source")


async def test_recall_source_context_searches_chunks_for_the_session_dataset(monkeypatch):
    search_mock = AsyncMock(return_value=["Quote from the PDF", "Another quote"])
    monkeypatch.setattr(cognee_svc.cognee, "search", search_mock)

    results = await cognee_svc.recall_source_context("s1", "is nuclear power safe?")

    search_mock.assert_awaited_once()
    kwargs = search_mock.call_args.kwargs
    assert kwargs["query_type"] == cognee_svc.SearchType.CHUNKS
    assert kwargs["datasets"] == ["session_s1_source"]
    assert kwargs["top_k"] == 5
    assert kwargs["query_text"] == "is nuclear power safe?"
    assert results == [{"text": "Quote from the PDF"}, {"text": "Another quote"}]


async def test_recall_source_context_returns_empty_list_when_dataset_missing(monkeypatch):
    async def _raise(*args, **kwargs):
        raise Exception("dataset not found")

    monkeypatch.setattr(cognee_svc.cognee, "search", _raise)

    results = await cognee_svc.recall_source_context("s1", "anything")

    assert results == []


async def test_index_source_document_raises_on_timeout(monkeypatch):
    async def _slow_add(*args, **kwargs):
        await asyncio.sleep(999)

    monkeypatch.setattr(cognee_svc.cognee, "add", _slow_add)
    monkeypatch.setattr(cognee_svc, "ADD_TIMEOUT", 0.01)

    with pytest.raises(asyncio.TimeoutError):
        await cognee_svc.index_source_document("s1", "/tmp/e.pdf")


async def test_recall_source_context_logs_error_and_returns_empty_on_failure(monkeypatch, caplog):
    import logging

    async def _raise(*args, **kwargs):
        raise RuntimeError("cognee misconfigured")

    monkeypatch.setattr(cognee_svc.cognee, "search", _raise)

    with caplog.at_level(logging.ERROR, logger="debatemind.services.cognee_svc"):
        results = await cognee_svc.recall_source_context("s1", "anything")

    assert results == []
    assert any(
        "recall_source_context" in r.message.lower() or "cognee" in r.message.lower()
        for r in caplog.records
    )
