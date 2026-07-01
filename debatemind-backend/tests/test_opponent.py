"""
Unit tests for opponent.generate_opponent — verifies weakness and source
context wiring. The OpenRouter LLM call and both Cognee recall functions are
mocked; no real network or Cognee calls happen here.
"""

from types import SimpleNamespace


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


def test_weakness_cache_has_bounded_size():
    from debatemind.agents.opponent import _weakness_cache

    # TTLCache has a maxsize attribute; plain dict does not
    assert hasattr(_weakness_cache, "maxsize")
    assert _weakness_cache.maxsize == 1024
