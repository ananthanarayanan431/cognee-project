# Prompt quality upgrade for extractor/judge/opponent

**Date:** 2026-06-30
**Status:** Approved

## Context

DebateMind's core value is delivered entirely through three LLM calls in
`debatemind/agents/`: `extractor` (classifies the user's argument pattern,
fallacy, and evidence quality), `judge` (scores the user/opponent exchange
and decides Won/Lost/Neutral), and `opponent` (generates the AI debate
opponent's counter-argument, targeting the user's known weaknesses). Since
the app has essentially no other "intelligence" layer, prompt quality *is*
product quality.

The current prompts (`debatemind/agents/prompts/{extractor,judge,opponent}.py`)
are bare f-strings: no role framing, no few-shot examples, no reasoning
structure, and — for `extractor`/`judge` — no enforced output schema. Both
of those return JSON that's parsed with `json.loads(...)` inside a bare
`try/except Exception` that silently falls back to generic defaults
(`pattern_type="EvidenceBased"`, all scores `5.0`, `outcome="Neutral"`) on
*any* parse failure, including markdown code fences or trailing commentary
the model might add. There's also no shared vocabulary for what the nine
`PATTERN_TYPES` in `constants.py` actually mean (e.g. `StrawMan` vs
`FalseEquivalence`) — the extractor prompt currently just lists the bare
names.

This was researched against Anthropic's current prompting guidance
(role prompting, XML-tag structuring, few-shot examples, chain-of-thought via
ordered output fields) and LLM-as-judge best practices (procedural rubric
anchors over bare adjectives/numbers, to counter known judge-ambiguity and
verbosity-bias failure modes), and against OpenRouter's structured-outputs
support (`response_format: {type: "json_schema", strict: true}`, supported by
both `anthropic/claude-haiku-4-5` and `anthropic/claude-sonnet-4-6`, the two
models this app uses).

Scope decisions made during design:
- All three prompt files are upgraded together for a consistent quality bar
  (per user's choice), but the LLM call sites in `debatemind/agents/*.py`
  only change for `extractor.py` and `judge.py` (adding `response_format`).
  `opponent.py`'s call site is untouched — it returns prose, not JSON.
- Structured outputs replace prompt-only JSON enforcement for `extractor`
  and `judge`. The existing `try/except` fallback in the call sites stays,
  but now only catches genuine infra failures (timeouts, network errors),
  not malformed-JSON failures, since the schema makes those structurally
  impossible.
- No live integration tests against OpenRouter (costs money, needs a live
  API key). Verification is schema-validity + prompt-rendering smoke tests.
- `PATTERN_TYPE_DESCRIPTIONS` is added to `constants.py` (not inlined in
  `extractor.py`) since `PATTERN_TYPES` is already imported by
  `graph_svc.py` and conceptually belongs with the existing list.

## Design

### 1. `constants.py` — pattern definitions

Add a parallel dict so the extractor prompt can give the classifier actual
definitions instead of bare labels:

```python
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

`PATTERN_TYPES` itself is untouched (other call sites iterate it as a plain
list of names).

### 2. `prompts/extractor.py` — classification prompt + schema

Rewritten with: a classifier role, XML-tagged input/taxonomy, 3 few-shot
examples spanning distinct categories, and a `reasoning` field placed first
in the schema so Claude reasons before committing to the label (its
generation order follows schema property order):

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

### 3. `prompts/judge.py` — scoring prompt + schema

The highest-risk prompt for LLM-judge failure modes, so it gets explicit
procedural rubric anchors (replacing bare "1-10") and an explicit,
deterministic outcome rule:

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

(Note: scores for both sides are derived via the `reasoning` field and the
single returned trio is the *user's* score, consistent with current
`DebateState` shape — `judge_logic`/`judge_evidence`/`judge_rhetoric` are
user-side fields today. The opponent's side is scored only internally,
within `reasoning`, to ground the `outcome` decision; no schema change to
`DebateState` needed.)

### 4. `prompts/opponent.py` — system/user prompt

Lighter-touch rewrite (this is prose generation, not JSON, and is on the
user-facing latency path with `main_model`) — sharper role framing, an XML
`<tactics>` block, and difficulty instructions stated as concrete moves
instead of adjectives:

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

### 5. Call site changes (`debatemind/agents/{extractor,judge}.py`)

Both add `response_format` to the `chat.completions.create(...)` call:

```python
msg = await openrouter.chat.completions.create(
    model=settings.fast_model,
    max_tokens=300,  # was 200 — schema now includes a reasoning field
    messages=[{"role": "user", "content": prompt}],
    response_format={"type": "json_schema", "json_schema": EXTRACTOR_RESPONSE_SCHEMA},
)
```

(same pattern for `judge.py` with `JUDGE_RESPONSE_SCHEMA`). `max_tokens` is
bumped 200 → 300 to leave room for the `reasoning` field text without
truncating the JSON. The existing `try/except Exception` fallback blocks are
otherwise unchanged — they remain the safety net for network/timeout
failures, not malformed-JSON failures.

`opponent.py`'s call site is unchanged (no `response_format`, it returns
free text).

### 6. Verification

No live OpenRouter calls (costs money, needs a real API key). Instead:

- A schema-validity check per `*_RESPONSE_SCHEMA`: confirms it's valid JSON
  Schema, `additionalProperties: false`, and `required` exactly matches
  `properties.keys()` (the precondition for strict mode).
- Prompt-rendering smoke tests: call `extractor_prompt(...)`,
  `judge_prompt(...)`, `opponent_system_prompt(...)`,
  `opponent_user_message(...)` with sample inputs and assert they render
  without error and contain the expected interpolated values (topic,
  argument text, weakness text).
- Manual read-through of each rendered prompt for the "show it to a
  colleague with no context" bar from Anthropic's guidance.

These land as a new `tests/test_prompts.py` (mirroring the existing
`tests/test_progress_svc.py` pattern in this repo).
