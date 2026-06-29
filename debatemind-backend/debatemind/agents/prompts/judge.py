def judge_prompt(topic: str, user_argument: str, opponent_argument: str) -> str:
    return f"""Score this debate exchange. Return JSON only.

Topic: {topic}
User: {user_argument}
Opponent: {opponent_argument}

Return exactly:
{{
  "logic": <1-10>,
  "evidence": <1-10>,
  "rhetoric": <1-10>,
  "fallacy": "<fallacy name or null>",
  "outcome": "<Won|Lost|Neutral>"
}}

Outcome = Won if user's argument is stronger, Lost if opponent's is stronger."""
