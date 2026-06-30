"""
Unit tests for opponent.generate_opponent — verifies weakness and source
context wiring. The OpenRouter LLM call and both Cognee recall functions are
mocked; no real network or Cognee calls happen here.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from debatemind.agents import opponent as opponent_module


def _state(**overrides) -> dict:
    base: dict = {
        "user_id": "u1",
        "session_id": "s1",
        "topic": "AI Safety",
        "description": "",
        "difficulty": "targeted",
        "user_position": "against",
        "user_message": "test argument",
        "turn_number": 1,
        "consecutive_wins": 0,
        "has_source": False,
        "source_context": [],
        "weakness_context": [],
        "extracted_pattern": None,
        "extracted_fallacy": None,
        "evidence_quality": None,
        "opponent_response": None,
        "judge_logic": None,
        "judge_evidence": None,
        "judge_rhetoric": None,
        "judge_fallacy": None,
        "outcome": None,
        "mastery_events": [],
    }
    base.update(overrides)
    return base


def _mock_llm_response(text="A counter-argument."):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


async def test_skips_source_recall_when_session_has_no_source(monkeypatch):
    opponent_module._weakness_cache.clear()
    monkeypatch.setattr(opponent_module, "recall_weaknesses", AsyncMock(return_value=[]))
    source_mock = AsyncMock()
    monkeypatch.setattr(opponent_module, "recall_source_context", source_mock)
    monkeypatch.setattr(
        opponent_module.openrouter.chat.completions,
        "create",
        AsyncMock(return_value=_mock_llm_response()),
    )

    await opponent_module.generate_opponent(_state(has_source=False))

    source_mock.assert_not_called()


async def test_fetches_and_includes_source_context_when_session_has_source(monkeypatch):
    opponent_module._weakness_cache.clear()
    monkeypatch.setattr(opponent_module, "recall_weaknesses", AsyncMock(return_value=[]))
    source_mock = AsyncMock(return_value=[{"text": "The report says X."}])
    monkeypatch.setattr(opponent_module, "recall_source_context", source_mock)
    llm_mock = AsyncMock(return_value=_mock_llm_response())
    monkeypatch.setattr(opponent_module.openrouter.chat.completions, "create", llm_mock)

    result = await opponent_module.generate_opponent(_state(has_source=True, session_id="s9"))

    source_mock.assert_awaited_once_with("s9", "test argument")
    assert result["source_context"] == [{"text": "The report says X."}]
    system_msg = llm_mock.call_args.kwargs["messages"][0]["content"]
    assert "The report says X." in system_msg


def test_weakness_cache_has_bounded_size():
    from debatemind.agents.opponent import _weakness_cache

    # TTLCache has a maxsize attribute; plain dict does not
    assert hasattr(_weakness_cache, "maxsize")
    assert _weakness_cache.maxsize == 1024
