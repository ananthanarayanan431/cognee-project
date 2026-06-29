"""
Unit tests for mastery.check_mastery — pure logic, no external I/O.
asyncio_mode = "auto" in pyproject.toml means no @pytest.mark.asyncio needed.
"""

from debatemind.agents.mastery import MASTERY_THRESHOLD, check_mastery


def _state(**overrides) -> dict:
    base: dict = {
        "user_id": "u1",
        "session_id": "s1",
        "topic": "AI Safety",
        "difficulty": "targeted",
        "user_position": "against",
        "user_message": "test argument",
        "turn_number": 1,
        "consecutive_wins": 0,
        "extracted_pattern": None,
        "extracted_fallacy": None,
        "evidence_quality": None,
        "weakness_context": [],
        "opponent_response": None,
        "judge_logic": None,
        "judge_evidence": None,
        "judge_rhetoric": None,
        "judge_fallacy": None,
        "outcome": None,
        "mastery_events": [],
        "_prev_pattern": None,
    }
    base.update(overrides)
    return base


async def test_mastery_events_reset_each_turn():
    state = _state(outcome="Lost", extracted_pattern="StrawMan", mastery_events=["OldPattern"])
    result = await check_mastery(state)
    assert result["mastery_events"] == []


async def test_no_mastery_on_loss():
    state = _state(outcome="Lost", extracted_pattern="StrawMan")
    result = await check_mastery(state)
    assert result["mastery_events"] == []
    assert result.get("wins_StrawMan", 0) == 0


async def test_win_increments_counter():
    state = _state(
        outcome="Won",
        extracted_pattern="AdHominem",
        _prev_pattern="AdHominem",
    )
    state["wins_AdHominem"] = 0
    result = await check_mastery(state)
    assert result.get("wins_AdHominem") == 1
    assert result["mastery_events"] == []


async def test_mastery_fires_at_threshold():
    state = _state(
        outcome="Won",
        extracted_pattern="AdHominem",
        _prev_pattern="AdHominem",
    )
    state["wins_AdHominem"] = MASTERY_THRESHOLD - 1
    result = await check_mastery(state)
    assert "AdHominem" in result["mastery_events"]
    assert result.get("wins_AdHominem", 0) == 0  # counter resets after mastery


async def test_no_mastery_one_win_below_threshold():
    state = _state(
        outcome="Won",
        extracted_pattern="SlipperySlope",
        _prev_pattern="SlipperySlope",
    )
    state["wins_SlipperySlope"] = MASTERY_THRESHOLD - 2
    result = await check_mastery(state)
    assert result["mastery_events"] == []


async def test_pattern_change_resets_wins():
    state = _state(
        outcome="Won",
        extracted_pattern="FalseEquivalence",
        _prev_pattern="StrawMan",  # changed
    )
    state["wins_StrawMan"] = 2  # prior pattern had 2 wins
    result = await check_mastery(state)
    # New pattern starts at 0 then gets +1 from the Won this turn
    assert result.get("wins_FalseEquivalence") == 1
    assert result["mastery_events"] == []


async def test_non_win_resets_counter():
    state = _state(
        outcome="Neutral",
        extracted_pattern="StrawMan",
        _prev_pattern="StrawMan",
    )
    state["wins_StrawMan"] = 2
    result = await check_mastery(state)
    assert result.get("wins_StrawMan", 0) == 0
    assert result["mastery_events"] == []
