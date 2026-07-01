from typing import Optional, TypedDict


class DebateState(TypedDict):
    user_id: str
    session_id: str
    topic: str
    description: Optional[str]
    difficulty: str
    user_position: str
    user_message: str
    turn_number: int
    consecutive_wins: int
    extracted_pattern: Optional[str]
    extracted_fallacy: Optional[str]
    evidence_quality: Optional[str]
    weakness_context: list[dict]
    opponent_response: Optional[str]
    judge_logic: Optional[float]
    judge_evidence: Optional[float]
    judge_rhetoric: Optional[float]
    judge_fallacy: Optional[str]
    outcome: Optional[str]
    mastery_events: list[str]
    _prev_pattern: Optional[str]  # mastery.py tracks pattern continuity across turns
