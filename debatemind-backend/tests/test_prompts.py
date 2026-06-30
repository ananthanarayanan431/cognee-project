"""Unit tests for prompt builders — pure string functions, no I/O."""

from debatemind.agents.constants import PATTERN_TYPE_DESCRIPTIONS, PATTERN_TYPES
from debatemind.agents.prompts.extractor import extractor_prompt
from debatemind.agents.prompts.judge import judge_prompt
from debatemind.agents.prompts.opponent import (
    _DIFFICULTY_INSTRUCTIONS,
    opponent_system_prompt,
    opponent_user_message,
)


class TestExtractorPrompt:
    def test_contains_topic_and_argument(self):
        p = extractor_prompt("Climate change", "We must cut emissions now")
        assert "Climate change" in p
        assert "We must cut emissions now" in p

    def test_contains_all_pattern_types(self):
        p = extractor_prompt("topic", "arg")
        for pattern in PATTERN_TYPES:
            assert pattern in p

    def test_requests_json_output(self):
        p = extractor_prompt("topic", "arg")
        assert "pattern_type" in p
        assert "fallacy" in p
        assert "evidence_quality" in p


class TestJudgePrompt:
    def test_contains_all_parties(self):
        p = judge_prompt("AI regulation", "more rules needed", "rules stifle innovation")
        assert "AI regulation" in p
        assert "more rules needed" in p
        assert "rules stifle innovation" in p

    def test_requests_score_fields(self):
        p = judge_prompt("t", "u", "o")
        for field in ("logic", "evidence", "rhetoric", "fallacy", "outcome"):
            assert field in p

    def test_win_condition_explained(self):
        p = judge_prompt("t", "u", "o")
        assert "Won" in p and "Lost" in p


class TestOpponentPrompts:
    def test_system_prompt_contains_weakness_text(self):
        p = opponent_system_prompt("tends to use anecdotes", "targeted")
        assert "tends to use anecdotes" in p

    def test_system_prompt_contains_difficulty(self):
        p = opponent_system_prompt("weakness A", "ruthless")
        assert "ruthless" in p

    def test_system_prompt_uses_correct_instruction(self):
        for difficulty, instruction in _DIFFICULTY_INSTRUCTIONS.items():
            p = opponent_system_prompt("x", difficulty)
            assert instruction in p

    def test_system_prompt_unknown_difficulty_falls_back_to_targeted(self):
        p = opponent_system_prompt("x", "nonexistent")
        assert _DIFFICULTY_INSTRUCTIONS["targeted"] in p

    def test_user_message_contains_topic_and_argument(self):
        m = opponent_user_message("Tax policy", "higher taxes reduce inequality")
        assert "Tax policy" in m
        assert "higher taxes reduce inequality" in m


class TestPatternTypeDescriptions:
    def test_has_a_description_for_every_pattern_type(self):
        assert set(PATTERN_TYPE_DESCRIPTIONS.keys()) == set(PATTERN_TYPES)

    def test_descriptions_are_non_empty_strings(self):
        for desc in PATTERN_TYPE_DESCRIPTIONS.values():
            assert isinstance(desc, str)
            assert len(desc) > 0
