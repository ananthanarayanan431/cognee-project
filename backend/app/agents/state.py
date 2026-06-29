from typing import TypedDict, Optional


class DebateState(TypedDict):
    user_id: str
    session_id: str
    topic: str
    difficulty: str
    user_position: str
    user_message: str
    turn_number: int
    consecutive_wins: int        # on current weakness
    extracted_pattern: Optional[str]
    extracted_fallacy: Optional[str]
    evidence_quality: Optional[str]
    weakness_context: list[dict]  # from recall()
    opponent_response: Optional[str]
    judge_logic: Optional[float]
    judge_evidence: Optional[float]
    judge_rhetoric: Optional[float]
    judge_fallacy: Optional[str]
    outcome: Optional[str]       # Won/Lost/Neutral
    mastery_events: list[str]    # patterns mastered this turn
