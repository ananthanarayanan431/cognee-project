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


def opponent_system_prompt(
    weakness_text: str,
    difficulty: str,
    user_position: str = "",
    source_text: str = "",
) -> str:
    instruction = _DIFFICULTY_INSTRUCTIONS.get(difficulty, _DIFFICULTY_INSTRUCTIONS["targeted"])

    position_label = user_position.lower() if user_position else "unspecified"
    if position_label == "assign_randomly":
        position_label = "unspecified"

    position_rule = (
        f"The user has committed to arguing **{position_label}** this motion for the entire "
        f"debate. If their argument contradicts their declared position, concedes the motion "
        f"entirely, or attempts to flip sides, call it out immediately — one sharp sentence "
        f"naming the inconsistency — before engaging the substance. "
        f"Never let position drift go unnoticed."
    )

    prompt = f"""You are a world-class debate opponent: sharp, well-read, and
unwilling to concede ground that hasn't been earned.

<position_rule>
{position_rule}
</position_rule>

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
        capped = source_text[:4000] + ("…" if len(source_text) > 4000 else "")
        prompt += (
            f"\n\n<source_material>\n"
            f"Source the user provided (cite specifics when relevant):\n{capped}"
            f"\n</source_material>"
        )
    return prompt


def opponent_user_message(
    topic: str,
    user_argument: str,
    description: str = "",
    user_position: str = "",
) -> str:
    context_line = f"\n\nContext: {description}" if description else ""
    position_label = user_position.lower() if user_position else ""
    if position_label == "assign_randomly":
        position_label = "unspecified"
    position_line = f"\nUser's declared position: {position_label}" if position_label else ""
    return f"Topic: {topic}{context_line}{position_line}\n\nUser argues: {user_argument}"
