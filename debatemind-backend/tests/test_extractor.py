"""Unit tests for agents.extractor.extract_argument — mocks the OpenRouter client."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from debatemind.agents import extractor
from debatemind.agents.prompts.extractor import EXTRACTOR_RESPONSE_SCHEMA


def _mock_completion(content: str | None):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def _state() -> dict:
    return {
        "topic": "AI regulation",
        "user_message": "Studies show stricter rules cut harm by half.",
    }


async def test_extract_argument_parses_structured_response(monkeypatch):
    create_mock = AsyncMock(
        return_value=_mock_completion(
            '{"reasoning": "Cites a study.", "pattern_type": "EvidenceBased", '
            '"fallacy": null, "evidence_quality": "Strong"}'
        )
    )
    monkeypatch.setattr(extractor.openrouter.chat.completions, "create", create_mock)

    result = await extractor.extract_argument(_state())

    assert result["extracted_pattern"] == "EvidenceBased"
    assert result["extracted_fallacy"] is None
    assert result["evidence_quality"] == "Strong"


async def test_extract_argument_requests_strict_json_schema(monkeypatch):
    create_mock = AsyncMock(
        return_value=_mock_completion(
            '{"reasoning": "x", "pattern_type": "EvidenceBased", '
            '"fallacy": null, "evidence_quality": "Moderate"}'
        )
    )
    monkeypatch.setattr(extractor.openrouter.chat.completions, "create", create_mock)

    await extractor.extract_argument(_state())

    _, kwargs = create_mock.call_args
    assert kwargs["response_format"] == {
        "type": "json_schema",
        "json_schema": EXTRACTOR_RESPONSE_SCHEMA,
    }
    assert kwargs["max_tokens"] == 300


async def test_extract_argument_falls_back_to_defaults_on_malformed_content(monkeypatch):
    create_mock = AsyncMock(return_value=_mock_completion(None))
    monkeypatch.setattr(extractor.openrouter.chat.completions, "create", create_mock)

    result = await extractor.extract_argument(_state())

    assert result["extracted_pattern"] == "EvidenceBased"
    assert result["extracted_fallacy"] is None
    assert result["evidence_quality"] == "Moderate"
