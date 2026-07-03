JUDGE_RESPONSE_SCHEMA = {
    "name": "debate_exchange_score",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "reasoning": {
                "type": "string",
                "description": (
                    "1-2 sentences: the specific strength/gap in each side "
                    "that drives the scores below."
                ),
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
was written — a longer, more assertive, or more confident-sounding answer is
not a better one, and neither is whichever argument happens to appear first.
Hold both sides to the identical standard, and do not let your own opinion of
the topic tilt the scores.

<rubric>
logic (does the reasoning chain actually hold together):
  1-3: bare assertion, no chain from premise to conclusion, or the chain
       breaks under the obvious objection
  4-6: a reasoning chain exists but skips a step or leans on an unstated
       assumption
  7-10: explicit premise-to-conclusion chain that anticipates and addresses
        the likely counter

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

Score each dimension independently: a strong score on one must not inflate the
others, and a single flaw should not drag down an otherwise sound dimension.
Reward the argument that directly engages the opponent's strongest point, and
penalize one that scores well on its own terms while sidestepping what it
actually needed to answer.

Score both sides against the rubric above, then decide outcome: sum each
side's logic+evidence+rhetoric; "Won" if the user's total exceeds the
opponent's by 3 or more, "Lost" if the opponent's exceeds the user's by 3 or
more, otherwise "Neutral". Also identify any fallacy present (or null)."""
