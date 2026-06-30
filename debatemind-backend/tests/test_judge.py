"""Unit tests for agents.judge.judge_exchange — mocks the OpenRouter client."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from debatemind.agents import judge
from debatemind.agents.prompts.judge import JUDGE_RESPONSE_SCHEMA


def _mock_completion(content: str | None):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def _state() -> dict:
    return {
        "topic": "AI regulation",
        "user_message": "Stricter rules cut harm by half per this study.",
        "opponent_response": "Regulation always lags behind the technology it targets.",
    }


async def test_judge_exchange_parses_structured_response(monkeypatch):
    create_mock = AsyncMock(
        return_value=_mock_completion(
            '{"reasoning": "User cites data.", "logic": 8, "evidence": 7, '
            '"rhetoric": 6, "fallacy": null, "outcome": "Won"}'
        )
    )
    monkeypatch.setattr(judge.openrouter.chat.completions, "create", create_mock)

    result = await judge.judge_exchange(_state())

    assert result["judge_logic"] == 8.0
    assert result["judge_evidence"] == 7.0
    assert result["judge_rhetoric"] == 6.0
    assert result["judge_fallacy"] is None
    assert result["outcome"] == "Won"


async def test_judge_exchange_requests_strict_json_schema(monkeypatch):
    payload = (
        '{"reasoning": "x", "logic": 5, "evidence": 5, "rhetoric": 5, '
        '"fallacy": null, "outcome": "Neutral"}'
    )
    create_mock = AsyncMock(return_value=_mock_completion(payload))
    monkeypatch.setattr(judge.openrouter.chat.completions, "create", create_mock)

    await judge.judge_exchange(_state())

    _, kwargs = create_mock.call_args
    assert kwargs["response_format"] == {
        "type": "json_schema",
        "json_schema": JUDGE_RESPONSE_SCHEMA,
    }
    assert kwargs["max_tokens"] == 300


async def test_judge_exchange_falls_back_to_defaults_on_malformed_content(monkeypatch):
    create_mock = AsyncMock(return_value=_mock_completion(None))
    monkeypatch.setattr(judge.openrouter.chat.completions, "create", create_mock)

    result = await judge.judge_exchange(_state())

    assert result["judge_logic"] == 5.0
    assert result["judge_evidence"] == 5.0
    assert result["judge_rhetoric"] == 5.0
    assert result["judge_fallacy"] is None
    assert result["outcome"] == "Neutral"
