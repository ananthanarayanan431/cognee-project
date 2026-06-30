_DIFFICULTY_INSTRUCTIONS = {
    "balanced": "Explore multiple angles; target a known weakness ~60% of the time.",
    "targeted": "Every response MUST target one of the user's listed weakness patterns.",
    "ruthless": "Hammer the same weakness from different angles until they find a true counter.",
}


def opponent_system_prompt(weakness_text: str, difficulty: str, source_text: str = "") -> str:
    instruction = _DIFFICULTY_INSTRUCTIONS.get(difficulty, _DIFFICULTY_INSTRUCTIONS["targeted"])
    prompt = f"""You are a world-class debate opponent.

User's cognitive fingerprint (known weaknesses):
{weakness_text}

Difficulty: {difficulty}
Instruction: {instruction}

Rules:
- Respond with a sharp, substantive counter-argument. No softening.
- Never concede unless the user's argument is genuinely irrefutable.
- Do NOT repeat an argument pattern you already used this session.
- Keep response under 120 words."""
    if source_text:
        prompt += (
            f"\n\nSource material the user provided "
            f"(cite specifics from this when relevant):\n{source_text}"
        )
    return prompt


def opponent_user_message(topic: str, user_argument: str, description: str = "") -> str:
    context_line = f"\n\nContext: {description}" if description else ""
    return f"Topic: {topic}{context_line}\n\nUser argues: {user_argument}"
