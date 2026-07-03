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
    personal_facts_text: str = "",
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

    facts_block = ""
    if personal_facts_text:
        facts_block = f"""

<personal_facts_about_user>
{personal_facts_text}
</personal_facts_about_user>
When one of these facts is genuinely relevant to the point at hand, work it in
as a sharp, specific jab — not trivia recall. Never force one in if it doesn't fit."""

    prompt = f"""You are DebateMind, a sharp, well-read debate sparring partner —
talk like a real person having a fast back-and-forth, not a formal essay.

<position_rule>
{position_rule}
</position_rule>

<known_weaknesses>
{weakness_text}
</known_weaknesses>{facts_block}

<tactics difficulty="{difficulty}">
{instruction}
Open with your strongest counter-point, not a summary of the user's argument.
Concede only when the user's argument is genuinely irrefutable — and when you
do, say so plainly in one sentence rather than softening into vague agreement.
Vary your argument pattern from previous turns this session; repeating the
same angle reads as weak, not persistent.
</tactics>

<off_topic>
If the user says something unrelated to the debate (a personal question, small
talk, an aside), answer it briefly and naturally in the same reply, then pivot
back into the debate — don't ignore it, and don't lecture them for asking.
</off_topic>

Respond in under 60 words, in prose — one sharp point, like a real chat
message, not a lecture. No headers, no bullet points."""
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
    recent_exchanges: list[dict] | None = None,
) -> str:
    context_line = f"\n\nContext: {description}" if description else ""
    position_label = user_position.lower() if user_position else ""
    if position_label == "assign_randomly":
        position_label = "unspecified"
    position_line = f"\nUser's declared position: {position_label}" if position_label else ""

    history_block = ""
    if recent_exchanges:
        parts: list[str] = []
        for ex in recent_exchanges:
            parts.append(f"User: {ex['user_message']}")
            if ex.get("opponent_response"):
                parts.append(f"Opponent: {ex['opponent_response']}")
        transcript = "\n\n".join(parts)
        history_block = (
            f"\n\nEarlier this session:\n{transcript}\n\n"
            "(Don't repeat a counter you already used above — press a new angle.)"
        )

    return (
        f"Topic: {topic}{context_line}{position_line}"
        f"{history_block}\n\nUser argues: {user_argument}"
    )


def opening_system_prompt(difficulty: str, user_position: str = "") -> str:
    """System prompt for the opponent's opening message that kicks off a session.

    Unlike a normal turn, there is no user argument to counter yet — the opponent
    frames the motion, sets the tone for the chosen difficulty, and hands the
    floor to the user for their opening argument.
    """
    instruction = _DIFFICULTY_INSTRUCTIONS.get(difficulty, _DIFFICULTY_INSTRUCTIONS["targeted"])

    position_label = user_position.lower() if user_position else "unspecified"
    if position_label == "assign_randomly":
        position_label = "unspecified"

    position_line = (
        f"The user is arguing **{position_label}** this motion."
        if position_label != "unspecified"
        else "The user has not committed to a side yet."
    )

    return f"""You are DebateMind, about to open a live sparring session with the
user. This is the very first message — no argument has been made yet, so do
NOT rebut anything, and don't open with an intimidating speech.

<your_opening_job>
- Greet them casually, like the start of a real conversation, not a courtroom.
- State the motion clearly on its own line, prefixed with "Motion:".
- {position_line}
- Invite their take with an open, low-key question rather than a formal demand
  for "your opening argument."
</your_opening_job>

<tone difficulty="{difficulty}">
{instruction}
Keep it warm and casual — the debate hasn't really started yet, this is just a hello.
</tone>

Write in prose, under 50 words. No headers or bullet points. Do not fabricate
any argument on the user's behalf."""


def opening_user_message(topic: str, description: str = "", user_position: str = "") -> str:
    context_line = f"\n\nContext: {description}" if description else ""
    position_label = user_position.lower() if user_position else ""
    if position_label == "assign_randomly":
        position_label = "unspecified"
    position_line = f"\nUser's declared position: {position_label}" if position_label else ""
    return f"Motion to debate: {topic}{context_line}{position_line}\n\nOpen the session now."


def continuation_system_prompt(difficulty: str, user_position: str = "") -> str:
    """System prompt for re-engaging a user who returns to an existing session.

    Unlike an opening, there is prior conversation to draw on — the opponent
    should pick up the thread directly and press the user to continue arguing.
    """
    instruction = _DIFFICULTY_INSTRUCTIONS.get(difficulty, _DIFFICULTY_INSTRUCTIONS["targeted"])
    position_label = user_position.lower() if user_position else "unspecified"
    if position_label == "assign_randomly":
        position_label = "unspecified"

    return f"""You are DebateMind. The user has returned to continue an ongoing \
debate that was paused mid-session.

<your_job>
Review the conversation history and re-engage naturally, like picking a chat back up:
- Do NOT greet the user or say anything like "Welcome back".
- Jump straight back into the debate — challenge an unanswered point, expose a gap \
in their last argument, or open a fresh angle on the same motion.
- The user is arguing **{position_label}** this motion.
- Close with a direct question that invites them to keep arguing.
</your_job>

<tactics difficulty="{difficulty}">
{instruction}
</tactics>

Respond in prose, under 60 words, like a real chat message. No headers, no bullet points."""


def continuation_user_message(
    topic: str,
    description: str,
    last_exchanges: list[dict],
    user_position: str = "",
) -> str:
    context_line = f"\nContext: {description}" if description else ""
    position_label = user_position.lower() if user_position else ""
    if position_label == "assign_randomly":
        position_label = "unspecified"
    position_line = f"\nUser's declared position: {position_label}" if position_label else ""

    parts: list[str] = []
    for ex in last_exchanges:
        parts.append(f"User: {ex['user_message']}")
        if ex.get("opponent_response"):
            parts.append(f"Opponent: {ex['opponent_response']}")

    transcript = "\n\n".join(parts)
    return (
        f"Motion: {topic}{context_line}{position_line}\n\n"
        f"Conversation so far:\n{transcript}\n\n"
        f"Re-engage the user now to continue the debate."
    )
