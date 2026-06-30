"""Unit tests for prompt builders — pure string functions, no I/O."""

from debatemind.agents.constants import PATTERN_TYPE_DESCRIPTIONS, PATTERN_TYPES
from debatemind.agents.prompts.extractor import EXTRACTOR_RESPONSE_SCHEMA, extractor_prompt
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

    def test_contains_all_pattern_types_and_descriptions(self):
        p = extractor_prompt("topic", "arg")
        for pattern, desc in PATTERN_TYPE_DESCRIPTIONS.items():
            assert pattern in p
            assert desc in p

    def test_has_role_framing(self):
        p = extractor_prompt("topic", "arg")
        assert "classifier" in p.lower()

    def test_has_few_shot_examples(self):
        p = extractor_prompt("topic", "arg")
        assert p.count("<example>") >= 3
        assert p.count("</example>") == p.count("<example>")


class TestExtractorSchema:
    def test_schema_is_strict_with_consistent_required_fields(self):
        body = EXTRACTOR_RESPONSE_SCHEMA["schema"]
        assert EXTRACTOR_RESPONSE_SCHEMA["strict"] is True
        assert body["additionalProperties"] is False
        assert set(body["required"]) == set(body["properties"].keys())

    def test_reasoning_field_is_first(self):
        first_key = next(iter(EXTRACTOR_RESPONSE_SCHEMA["schema"]["properties"]))
        assert first_key == "reasoning"

    def test_pattern_type_enum_matches_constants(self):
        assert (  # noqa: E501
            EXTRACTOR_RESPONSE_SCHEMA["schema"]["properties"]["pattern_type"]["enum"]
            == PATTERN_TYPES
        )


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
