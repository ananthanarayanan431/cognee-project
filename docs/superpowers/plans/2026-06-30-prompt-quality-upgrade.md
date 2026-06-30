# Prompt Quality Upgrade (extractor/judge/opponent) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade DebateMind's three LLM prompts (extractor, judge, opponent) to follow Anthropic's current prompting best practices and LLM-as-judge rubric design, and make the extractor/judge outputs schema-enforced via OpenRouter structured outputs instead of bare `json.loads` + silent fallback.

**Architecture:** Prompt text and its JSON schema live together in each `debatemind/agents/prompts/*.py` file. The two agent call sites (`debatemind/agents/extractor.py`, `debatemind/agents/judge.py`) pass the schema as `response_format` to `openrouter.chat.completions.create(...)`. No new runtime dependencies, no `DebateState` shape changes, no API/router changes.

**Tech Stack:** Python 3.12, pytest (`asyncio_mode = "auto"`), OpenAI-compatible `AsyncOpenAI` client routed through OpenRouter to `anthropic/claude-haiku-4-5` (fast_model) and `anthropic/claude-sonnet-4-6` (main_model), both of which support `response_format: {"type": "json_schema", "strict": true}`.

## Global Constraints

- Source of truth for this plan is `docs/superpowers/specs/2026-06-30-prompt-quality-upgrade-design.md` — copy prompt/schema text from there verbatim; don't improvise wording mid-implementation.
- `PATTERN_TYPES` (the plain list in `debatemind/agents/constants.py`) must NOT change — `debatemind/services/graph_svc.py` iterates it as-is.
- `DebateState` (`debatemind/agents/state.py`) is unchanged — no new keys.
- Test commands run from `debatemind-backend/` using `.venv/bin/python -m pytest <path> -v`.
- Existing `try/except Exception` fallback blocks in `extractor.py`/`judge.py` call sites stay in place (infra-failure safety net) — do not remove them.

---

### Task 1: Pattern type descriptions in `constants.py`

**Files:**
- Modify: `debatemind-backend/debatemind/agents/constants.py`
- Test: `debatemind-backend/tests/test_prompts.py`

**Interfaces:**
- Produces: `PATTERN_TYPE_DESCRIPTIONS: dict[str, str]` in `debatemind.agents.constants`, with exactly the same keys as `PATTERN_TYPES` (same module).

- [ ] **Step 1: Write the failing test**

Add to `debatemind-backend/tests/test_prompts.py` (new import + new test class — place near the top, after existing imports):

```python
from debatemind.agents.constants import PATTERN_TYPE_DESCRIPTIONS, PATTERN_TYPES
```

```python
class TestPatternTypeDescriptions:
    def test_has_a_description_for_every_pattern_type(self):
        assert set(PATTERN_TYPE_DESCRIPTIONS.keys()) == set(PATTERN_TYPES)

    def test_descriptions_are_non_empty_strings(self):
        for desc in PATTERN_TYPE_DESCRIPTIONS.values():
            assert isinstance(desc, str)
            assert len(desc) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd debatemind-backend && .venv/bin/python -m pytest tests/test_prompts.py::TestPatternTypeDescriptions -v`
Expected: ERROR (collection failure for the whole file, since the new import is at module level) — `ImportError: cannot import name 'PATTERN_TYPE_DESCRIPTIONS'`

- [ ] **Step 3: Add `PATTERN_TYPE_DESCRIPTIONS` to `constants.py`**

`debatemind-backend/debatemind/agents/constants.py` becomes:

```python
PATTERN_TYPES = [
    "EvidenceBased",
    "AppealToAuthority",
    "StrawMan",
    "AdHominem",
    "SlipperySlope",
    "FalseEquivalence",
    "EmotionalAppeal",
    "AnecdotalEvidence",
    "Concession",
]

PATTERN_TYPE_DESCRIPTIONS: dict[str, str] = {
    "EvidenceBased": "Claim is supported by cited facts, data, or named sources.",
    "AppealToAuthority": "Claim leans on a person's/institution's status rather than the reasoning itself.",
    "StrawMan": "Misrepresents or exaggerates the opposing position before refuting the misrepresentation.",
    "AdHominem": "Attacks the arguer's character/motives instead of the argument's substance.",
    "SlipperySlope": "Asserts an extreme outcome will follow from a moderate action without showing the causal chain.",
    "FalseEquivalence": "Treats two meaningfully different things as morally/logically equivalent.",
    "EmotionalAppeal": "Leans on fear, outrage, or sympathy in place of evidence or logic.",
    "AnecdotalEvidence": "Generalizes from a single personal story or isolated case.",
    "Concession": "Partially or fully accepts the opposing point rather than contesting it.",
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd debatemind-backend && .venv/bin/python -m pytest tests/test_prompts.py::TestPatternTypeDescriptions -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
cd /Volumes/External/hackathon
git add debatemind-backend/debatemind/agents/constants.py debatemind-backend/tests/test_prompts.py
git commit -m "feat: add pattern type descriptions for extractor prompt"
```

---

### Task 2: Rewrite `extractor.py` prompt with schema, role, examples

**Files:**
- Modify: `debatemind-backend/debatemind/agents/prompts/extractor.py`
- Modify: `debatemind-backend/tests/test_prompts.py`

**Interfaces:**
- Consumes: `PATTERN_TYPE_DESCRIPTIONS`, `PATTERN_TYPES` from `debatemind.agents.constants` (Task 1).
- Produces: `EXTRACTOR_RESPONSE_SCHEMA: dict` and `extractor_prompt(topic: str, argument: str) -> str` (same signature as before) in `debatemind.agents.prompts.extractor`.

- [ ] **Step 1: Write the failing tests**

Replace the `TestExtractorPrompt` class in `debatemind-backend/tests/test_prompts.py` with:

```python
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
        assert EXTRACTOR_RESPONSE_SCHEMA["schema"]["properties"]["pattern_type"]["enum"] == PATTERN_TYPES
```

Update the import block at the top of the file to:

```python
from debatemind.agents.constants import PATTERN_TYPE_DESCRIPTIONS, PATTERN_TYPES
from debatemind.agents.prompts.extractor import EXTRACTOR_RESPONSE_SCHEMA, extractor_prompt
from debatemind.agents.prompts.judge import judge_prompt
from debatemind.agents.prompts.opponent import (
    _DIFFICULTY_INSTRUCTIONS,
    opponent_system_prompt,
    opponent_user_message,
)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd debatemind-backend && .venv/bin/python -m pytest tests/test_prompts.py::TestExtractorPrompt tests/test_prompts.py::TestExtractorSchema -v`
Expected: ERROR (collection failure for the whole file) — `ImportError: cannot import name 'EXTRACTOR_RESPONSE_SCHEMA'` (old `extractor.py` doesn't define it yet)

- [ ] **Step 3: Rewrite `debatemind-backend/debatemind/agents/prompts/extractor.py`**

```python
from debatemind.agents.constants import PATTERN_TYPE_DESCRIPTIONS, PATTERN_TYPES

EXTRACTOR_RESPONSE_SCHEMA = {
    "name": "argument_classification",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "reasoning": {
                "type": "string",
                "description": "One sentence: what about this argument drives the classification below.",
            },
            "pattern_type": {"type": "string", "enum": PATTERN_TYPES},
            "fallacy": {"type": ["string", "null"]},
            "evidence_quality": {
                "type": "string",
                "enum": ["Strong", "Moderate", "Weak", "Absent"],
            },
        },
        "required": ["reasoning", "pattern_type", "fallacy", "evidence_quality"],
        "additionalProperties": False,
    },
}


def extractor_prompt(topic: str, argument: str) -> str:
    pattern_list = "\n".join(f"- {name}: {desc}" for name, desc in PATTERN_TYPE_DESCRIPTIONS.items())
    return f"""You are a rigorous debate-pattern classifier. You read one
argument turn and identify its dominant rhetorical pattern, any logical
fallacy present, and the strength of its evidence — strictly as the
argument was written, not as you'd ideally want it written.

<pattern_types>
{pattern_list}
</pattern_types>

<examples>
<example>
<topic>Should cities ban single-use plastic bags?</topic>
<argument>My neighbor switched to reusable bags and said her grocery bill went down, so banning plastic bags clearly saves families money.</argument>
<output>{{"reasoning": "Generalizes a policy-wide economic claim from one neighbor's anecdote.", "pattern_type": "AnecdotalEvidence", "fallacy": "Hasty Generalization", "evidence_quality": "Weak"}}</output>
</example>
<example>
<topic>Should remote work be the default for office jobs?</topic>
<argument>A 2023 Stanford study tracking 16,000 workers found remote employees were 13% more productive and had measurably lower attrition.</argument>
<output>{{"reasoning": "Cites a specific, named, measurable study directly supporting the claim.", "pattern_type": "EvidenceBased", "fallacy": null, "evidence_quality": "Strong"}}</output>
</example>
<example>
<topic>Should the voting age be lowered to 16?</topic>
<argument>Anyone who opposes this clearly doesn't trust young people or believe in democracy.</argument>
<output>{{"reasoning": "Recasts opponents' position as bad faith rather than engaging their actual argument.", "pattern_type": "StrawMan", "fallacy": "Strawman", "evidence_quality": "Absent"}}</output>
</example>
</examples>

<topic>{topic}</topic>
<argument>{argument}</argument>

Classify the argument above using only the pattern types listed."""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd debatemind-backend && .venv/bin/python -m pytest tests/test_prompts.py -v`
Expected: all pass (existing 11 + new ones from Task 1 and Task 2)

- [ ] **Step 5: Commit**

```bash
cd /Volumes/External/hackathon
git add debatemind-backend/debatemind/agents/prompts/extractor.py debatemind-backend/tests/test_prompts.py
git commit -m "feat: rewrite extractor prompt with role, examples, and strict JSON schema"
```

---

### Task 3: Rewrite `judge.py` prompt with rubric anchors and schema

**Files:**
- Modify: `debatemind-backend/debatemind/agents/prompts/judge.py`
- Modify: `debatemind-backend/tests/test_prompts.py`

**Interfaces:**
- Produces: `JUDGE_RESPONSE_SCHEMA: dict` and `judge_prompt(topic: str, user_argument: str, opponent_argument: str) -> str` (same signature as before) in `debatemind.agents.prompts.judge`.

- [ ] **Step 1: Write the failing tests**

Replace the `TestJudgePrompt` class in `debatemind-backend/tests/test_prompts.py` with:

```python
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
        assert "Won" in p and "Lost" in p and "Neutral" in p

    def test_has_rubric_anchors_for_each_dimension(self):
        p = judge_prompt("t", "u", "o")
        assert "<rubric>" in p and "</rubric>" in p
        for dimension in ("logic", "evidence", "rhetoric"):
            assert dimension in p

    def test_warns_against_verbosity_bias(self):
        p = judge_prompt("t", "u", "o")
        assert "longer" in p.lower()


class TestJudgeSchema:
    def test_schema_is_strict_with_consistent_required_fields(self):
        body = JUDGE_RESPONSE_SCHEMA["schema"]
        assert JUDGE_RESPONSE_SCHEMA["strict"] is True
        assert body["additionalProperties"] is False
        assert set(body["required"]) == set(body["properties"].keys())

    def test_reasoning_field_is_first(self):
        first_key = next(iter(JUDGE_RESPONSE_SCHEMA["schema"]["properties"]))
        assert first_key == "reasoning"

    def test_outcome_enum_is_won_lost_neutral(self):
        assert JUDGE_RESPONSE_SCHEMA["schema"]["properties"]["outcome"]["enum"] == ["Won", "Lost", "Neutral"]
```

Update the import block at the top of `test_prompts.py` to add `JUDGE_RESPONSE_SCHEMA`:

```python
from debatemind.agents.prompts.judge import JUDGE_RESPONSE_SCHEMA, judge_prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd debatemind-backend && .venv/bin/python -m pytest tests/test_prompts.py::TestJudgePrompt tests/test_prompts.py::TestJudgeSchema -v`
Expected: ERROR (collection failure for the whole file) — `ImportError: cannot import name 'JUDGE_RESPONSE_SCHEMA'`

- [ ] **Step 3: Rewrite `debatemind-backend/debatemind/agents/prompts/judge.py`**

```python
JUDGE_RESPONSE_SCHEMA = {
    "name": "debate_exchange_score",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "reasoning": {
                "type": "string",
                "description": "1-2 sentences: the specific strength/gap in each side that drives the scores below.",
            },
            "logic": {"type": "integer", "minimum": 1, "maximum": 10},
            "evidence": {"type": "integer", "minimum": 1, "maximum": 10},
            "rhetoric": {"type": "integer", "minimum": 1, "maximum": 10},
            "fallacy": {"type": ["string", "null"]},
            "outcome": {"type": "string", "enum": ["Won", "Lost", "Neutral"]},
        },
        "required": ["reasoning", "logic", "evidence", "rhetoric", "fallacy", "outcome"],
        "additionalProperties": False,
    },
}


def judge_prompt(topic: str, user_argument: str, opponent_argument: str) -> str:
    return f"""You are an impartial debate judge. Score the user's argument
against the opponent's on this exchange. Judge only the substance of what
was written — a longer or more confident-sounding answer is not a better
one.

<rubric>
logic (does the reasoning chain actually hold together):
  1-3: bare assertion, no chain from premise to conclusion, or the chain breaks under the obvious objection
  4-6: a reasoning chain exists but skips a step or leans on an unstated assumption
  7-10: explicit premise-to-conclusion chain that anticipates and addresses the likely counter

evidence (specificity and relevance of support cited):
  1-3: no evidence offered, or pure opinion/anecdote
  4-6: evidence present but vague, unsourced, or only loosely relevant
  7-10: specific, attributable, directly relevant evidence (named source, data, mechanism)

rhetoric (persuasive craft, independent of logic/evidence):
  1-3: incoherent, off-topic, or purely hostile
  4-6: clear and on-topic but unremarkable
  7-10: precise framing that directly defuses the opponent's strongest point
</rubric>

<topic>{topic}</topic>
<user_argument>{user_argument}</user_argument>
<opponent_argument>{opponent_argument}</opponent_argument>

Score both sides against the rubric above, then decide outcome: sum each
side's logic+evidence+rhetoric; "Won" if the user's total exceeds the
opponent's by 3 or more, "Lost" if the opponent's exceeds the user's by 3 or
more, otherwise "Neutral"."""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd debatemind-backend && .venv/bin/python -m pytest tests/test_prompts.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
cd /Volumes/External/hackathon
git add debatemind-backend/debatemind/agents/prompts/judge.py debatemind-backend/tests/test_prompts.py
git commit -m "feat: rewrite judge prompt with procedural rubric anchors and strict JSON schema"
```

---

### Task 4: Rewrite `opponent.py` prompt (role, tactics, concrete difficulty instructions)

**Files:**
- Modify: `debatemind-backend/debatemind/agents/prompts/opponent.py`
- Modify: `debatemind-backend/tests/test_prompts.py`

**Interfaces:**
- Produces: `_DIFFICULTY_INSTRUCTIONS: dict[str, str]`, `opponent_system_prompt(weakness_text: str, difficulty: str) -> str`, `opponent_user_message(topic: str, user_argument: str) -> str` (same signatures as before) in `debatemind.agents.prompts.opponent`.

- [ ] **Step 1: Write the failing tests**

Replace the `TestOpponentPrompts` class in `debatemind-backend/tests/test_prompts.py` with:

```python
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

    def test_system_prompt_has_role_and_tactics_block(self):
        p = opponent_system_prompt("x", "targeted")
        assert "debate opponent" in p.lower()
        assert "<tactics" in p and "</tactics>" in p

    def test_user_message_contains_topic_and_argument(self):
        m = opponent_user_message("Tax policy", "higher taxes reduce inequality")
        assert "Tax policy" in m
        assert "higher taxes reduce inequality" in m
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd debatemind-backend && .venv/bin/python -m pytest tests/test_prompts.py::TestOpponentPrompts -v`
Expected: FAIL on `test_system_prompt_has_role_and_tactics_block` (no `<tactics` tag in current prompt yet); other tests still pass against the old prompt.

- [ ] **Step 3: Rewrite `debatemind-backend/debatemind/agents/prompts/opponent.py`**

```python
_DIFFICULTY_INSTRUCTIONS = {
    "balanced": "Explore multiple angles on the topic; bring in one of the user's listed weaknesses in roughly 6 of every 10 responses, not every turn.",
    "targeted": "Every response must exploit one specific weakness from the user's listed patterns — name the gap implicitly through your counter, not by quoting the label.",
    "ruthless": "Stay on the same weakness across consecutive turns, attacking it from a new angle each time, until the user produces a counter that actually closes the gap.",
}


def opponent_system_prompt(weakness_text: str, difficulty: str) -> str:
    instruction = _DIFFICULTY_INSTRUCTIONS.get(difficulty, _DIFFICULTY_INSTRUCTIONS["targeted"])
    return f"""You are a world-class debate opponent: sharp, well-read, and
unwilling to concede ground that hasn't been earned.

<known_weaknesses>
{weakness_text}
</known_weaknesses>

<tactics difficulty="{difficulty}">
{instruction}
Open with your strongest counter-point, not a summary of the user's argument.
Concede only when the user's argument is genuinely irrefutable — and when you
do, say so plainly in one sentence rather than softening into vague agreement.
Vary your argument pattern from previous turns this session; repeating the
same angle reads as weak, not persistent.
</tactics>

Respond in under 120 words, in prose — no headers, no bullet points."""


def opponent_user_message(topic: str, user_argument: str) -> str:
    return f"Topic: {topic}\n\nUser argues: {user_argument}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd debatemind-backend && .venv/bin/python -m pytest tests/test_prompts.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
cd /Volumes/External/hackathon
git add debatemind-backend/debatemind/agents/prompts/opponent.py debatemind-backend/tests/test_prompts.py
git commit -m "feat: rewrite opponent prompt with tactics block and concrete difficulty instructions"
```

---

### Task 5: Wire structured output into `agents/extractor.py`

**Files:**
- Modify: `debatemind-backend/debatemind/agents/extractor.py`
- Create: `debatemind-backend/tests/test_extractor.py`

**Interfaces:**
- Consumes: `EXTRACTOR_RESPONSE_SCHEMA`, `extractor_prompt` from `debatemind.agents.prompts.extractor` (Task 2).
- Produces: `extract_argument(state: DebateState) -> DebateState` (same signature as before; now sends `response_format` and `max_tokens=300`).

- [ ] **Step 1: Write the failing test**

Create `debatemind-backend/tests/test_extractor.py`:

```python
"""Unit tests for agents.extractor.extract_argument — mocks the OpenRouter client."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from debatemind.agents import extractor
from debatemind.agents.prompts.extractor import EXTRACTOR_RESPONSE_SCHEMA


def _mock_completion(content: str | None):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def _state() -> dict:
    return {"topic": "AI regulation", "user_message": "Studies show stricter rules cut harm by half."}


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
            '{"reasoning": "x", "pattern_type": "EvidenceBased", "fallacy": null, "evidence_quality": "Moderate"}'
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd debatemind-backend && .venv/bin/python -m pytest tests/test_extractor.py -v`
Expected: FAIL on `test_extract_argument_requests_strict_json_schema` — `KeyError: 'response_format'` (call site doesn't pass it yet)

- [ ] **Step 3: Update `debatemind-backend/debatemind/agents/extractor.py`**

```python
import json

from debatemind.agents.client import openrouter
from debatemind.agents.prompts.extractor import EXTRACTOR_RESPONSE_SCHEMA, extractor_prompt
from debatemind.agents.state import DebateState
from debatemind.config import settings


async def extract_argument(state: DebateState) -> DebateState:
    prompt = extractor_prompt(state["topic"], state["user_message"])
    msg = await openrouter.chat.completions.create(
        model=settings.fast_model,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_schema", "json_schema": EXTRACTOR_RESPONSE_SCHEMA},
    )
    try:
        data = json.loads(msg.choices[0].message.content or "")
        state["extracted_pattern"] = data.get("pattern_type", "EvidenceBased")
        state["extracted_fallacy"] = data.get("fallacy")
        state["evidence_quality"] = data.get("evidence_quality", "Moderate")
    except Exception:
        state["extracted_pattern"] = "EvidenceBased"
        state["extracted_fallacy"] = None
        state["evidence_quality"] = "Moderate"
    return state
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd debatemind-backend && .venv/bin/python -m pytest tests/test_extractor.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
cd /Volumes/External/hackathon
git add debatemind-backend/debatemind/agents/extractor.py debatemind-backend/tests/test_extractor.py
git commit -m "feat: enforce extractor JSON schema via OpenRouter structured outputs"
```

---

### Task 6: Wire structured output into `agents/judge.py`

**Files:**
- Modify: `debatemind-backend/debatemind/agents/judge.py`
- Create: `debatemind-backend/tests/test_judge.py`

**Interfaces:**
- Consumes: `JUDGE_RESPONSE_SCHEMA`, `judge_prompt` from `debatemind.agents.prompts.judge` (Task 3).
- Produces: `judge_exchange(state: DebateState) -> DebateState` (same signature as before; now sends `response_format` and `max_tokens=300`).

- [ ] **Step 1: Write the failing test**

Create `debatemind-backend/tests/test_judge.py`:

```python
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
            '{"reasoning": "User cites data, opponent asserts.", "logic": 8, "evidence": 7, '
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
    create_mock = AsyncMock(
        return_value=_mock_completion(
            '{"reasoning": "x", "logic": 5, "evidence": 5, "rhetoric": 5, "fallacy": null, "outcome": "Neutral"}'
        )
    )
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd debatemind-backend && .venv/bin/python -m pytest tests/test_judge.py -v`
Expected: FAIL on `test_judge_exchange_requests_strict_json_schema` — `KeyError: 'response_format'`

- [ ] **Step 3: Update `debatemind-backend/debatemind/agents/judge.py`**

```python
import json

from debatemind.agents.client import openrouter
from debatemind.agents.prompts.judge import JUDGE_RESPONSE_SCHEMA, judge_prompt
from debatemind.agents.state import DebateState
from debatemind.config import settings


async def judge_exchange(state: DebateState) -> DebateState:
    prompt = judge_prompt(state["topic"], state["user_message"], state["opponent_response"])
    msg = await openrouter.chat.completions.create(
        model=settings.fast_model,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_schema", "json_schema": JUDGE_RESPONSE_SCHEMA},
    )
    try:
        data = json.loads(msg.choices[0].message.content or "")
        state["judge_logic"] = float(data.get("logic", 5))
        state["judge_evidence"] = float(data.get("evidence", 5))
        state["judge_rhetoric"] = float(data.get("rhetoric", 5))
        state["judge_fallacy"] = data.get("fallacy")
        state["outcome"] = data.get("outcome", "Neutral")
    except Exception:
        state["judge_logic"] = 5.0
        state["judge_evidence"] = 5.0
        state["judge_rhetoric"] = 5.0
        state["judge_fallacy"] = None
        state["outcome"] = "Neutral"
    return state
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd debatemind-backend && .venv/bin/python -m pytest tests/test_judge.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
cd /Volumes/External/hackathon
git add debatemind-backend/debatemind/agents/judge.py debatemind-backend/tests/test_judge.py
git commit -m "feat: enforce judge JSON schema via OpenRouter structured outputs"
```

---

### Task 7: Full-suite verification and manual prompt read-through

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend test suite**

Run: `cd debatemind-backend && .venv/bin/python -m pytest -v`
Expected: all tests pass, including the pre-existing `test_mastery.py`, `test_progress_svc.py`, `test_graph_svc.py`, `test_cognee_svc.py`, `test_cognee_config.py`, `test_graph_schemas.py`, `test_config.py` (unaffected by this work) plus the new/updated `test_prompts.py`, `test_extractor.py`, `test_judge.py`.

- [ ] **Step 2: Manually read each rendered prompt**

```bash
cd debatemind-backend && .venv/bin/python -c "
from debatemind.agents.prompts.extractor import extractor_prompt
from debatemind.agents.prompts.judge import judge_prompt
from debatemind.agents.prompts.opponent import opponent_system_prompt, opponent_user_message

print('=== EXTRACTOR ===')
print(extractor_prompt('Should social media be regulated like a public utility?', 'Without regulation, a handful of companies control public discourse — that concentration of power is itself the harm, regardless of any single bad outcome.'))
print()
print('=== JUDGE ===')
print(judge_prompt('Should social media be regulated like a public utility?', 'Concentration of power over discourse is itself the harm.', 'Utility regulation assumes a natural monopoly; social media has competitors, so the analogy fails.'))
print()
print('=== OPPONENT SYSTEM ===')
print(opponent_system_prompt('Relies on anecdotes instead of data; concedes too quickly under pressure.', 'targeted'))
print()
print('=== OPPONENT USER ===')
print(opponent_user_message('Should social media be regulated like a public utility?', 'Concentration of power over discourse is itself the harm.'))
"
```

Read each printed prompt as if you were a colleague with no context on this codebase (the "golden rule" from Anthropic's prompting guide). Confirm: no contradictory instructions, no undefined terms, JSON examples are syntactically valid, and the rubric/tactics text reads as concrete procedures rather than vague adjectives. No code changes expected from this step — it's a final quality gate, not a TDD step.

- [ ] **Step 3: Confirm no leftover work**

```bash
cd /Volumes/External/hackathon && git status --short
```

Expected: clean (everything from Tasks 1–6 already committed).

---

## Self-Review Notes

- **Spec coverage:** constants.py (Task 1) ✓, extractor.py prompt+schema (Task 2) ✓, judge.py prompt+schema (Task 3) ✓, opponent.py prompt (Task 4) ✓, extractor.py call site (Task 5) ✓, judge.py call site (Task 6) ✓, schema-validity tests (Tasks 2–3) ✓, prompt-rendering smoke tests (all tasks via `test_prompts.py`) ✓, manual read-through (Task 7) ✓. No live OpenRouter integration tests, per spec.
- **Type consistency:** `extractor_prompt(topic: str, argument: str) -> str`, `judge_prompt(topic: str, user_argument: str, opponent_argument: str) -> str`, `opponent_system_prompt(weakness_text: str, difficulty: str) -> str`, `opponent_user_message(topic: str, user_argument: str) -> str` — all signatures match their pre-existing call sites in `debatemind/agents/{extractor,judge,opponent}.py` and `tests/test_prompts.py`, unchanged across tasks.
- **No placeholders:** every step has complete code, no TBD/TODO markers.
