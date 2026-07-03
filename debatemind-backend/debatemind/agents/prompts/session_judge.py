SESSION_JUDGE_RESPONSE_SCHEMA = {
    "name": "debate_session_score",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "reasoning": {
                "type": "string",
                "description": (
                    "2-3 sentences: the overall arc of the user's performance — "
                    "what drove the score up or down across the session."
                ),
            },
            "score": {"type": "number", "minimum": 1, "maximum": 10},
        },
        "required": ["reasoning", "score"],
        "additionalProperties": False,
    },
}


def session_judge_prompt(
    topic: str,
    description: str,
    difficulty: str,
    user_position: str,
    transcript: str,
) -> str:
    return f"""You are an impartial debate judge scoring a user's performance
across an entire debate session. Judge only the substance of what the user
wrote — length, assertiveness, or confident tone is not quality, and your own
opinion of the topic must not tilt the score.

The transcript below includes per-exchange judge scores (logic, evidence,
rhetoric, each 1-10) and outcomes recorded at the time. Treat them as
advisory context from a per-turn judge who could not see the whole session;
your job is the session-level view they could not take.

<rubric>
Score the user's overall session performance on a single 1-10 scale:
  1-3: arguments were bare assertions or collapsed under the opponent's
       counters; no recovery or adaptation across turns
  4-6: coherent arguments with real support, but gaps the opponent exploited
       went unrepaired, or quality was flat/declining across turns
  7-10: sustained premise-to-conclusion reasoning with specific evidence,
        direct engagement with the opponent's strongest points, and visible
        adaptation as the debate developed
</rubric>

Weigh in particular:
- consistency: did the user hold a coherent line across turns, or contradict
  themselves?
- engagement: did later turns answer the opponent's strongest prior points,
  or sidestep them?
- trajectory: reward a user who adapted and improved over the session;
  penalize one who repeated a refuted argument unchanged.

<topic>{topic}</topic>
<topic_description>{description}</topic_description>
<difficulty>{difficulty}</difficulty>
<user_position>{user_position}</user_position>

<transcript>
{transcript}
</transcript>

Return the single session score (one decimal allowed) and your reasoning."""
