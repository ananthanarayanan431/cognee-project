_DIFFICULTY_INSTRUCTIONS = {
    "balanced": (
        "Explore multiple angles on the topic; bring in one of the user's listed "
        "weaknesses in roughly 6 of every 10 responses, not every turn."
    ),
    "targeted": (
        "Every response must exploit one specific weakness from the user's listed "
        "patterns — name the gap implicitly through your counter, not by quoting "
        "the label."
    ),
    "ruthless": (
        "Stay on the same weakness across consecutive turns, attacking it from a new "
        "angle each time, until the user produces a counter that actually closes the gap."
    ),
}


def opponent_system_prompt(weakness_text: str, difficulty: str, source_text: str = "") -> str:
    instruction = _DIFFICULTY_INSTRUCTIONS.get(difficulty, _DIFFICULTY_INSTRUCTIONS["targeted"])
    prompt = f"""You are a world-class debate opponent: sharp, well-read, and
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
    if source_text:
        prompt += (
            f"\n\nSource material the user provided "
            f"(cite specifics from this when relevant):\n{source_text}"
        )
    return prompt


def opponent_user_message(topic: str, user_argument: str, description: str = "") -> str:
    context_line = f"\n\nContext: {description}" if description else ""
    return f"Topic: {topic}{context_line}\n\nUser argues: {user_argument}"
