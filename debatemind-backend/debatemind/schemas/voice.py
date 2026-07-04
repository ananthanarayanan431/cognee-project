from typing import Literal, Optional

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class TranscriptLineIn(BaseModel):
    voice_session_id: str
    speaker: Literal["user", "ai"]
    text: str


class ToolCallIn(BaseModel):
    voice_session_id: str
    tool: str
    arguments: dict = {}


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class TranscriptLineOut(BaseModel):
    speaker: Literal["user", "ai"]
    text: str


class VoiceSessionSummaryOut(BaseModel):
    has_voice_session: bool
    voice_session_id: Optional[str] = None
    status: Optional[str] = None
    duration_seconds: Optional[float] = None
    closing_summary: Optional[str] = None
    transcript: list[TranscriptLineOut] = []
    fallacies: list[str] = []
    strong_arguments: list[str] = []
    concessions: list[str] = []
    position_flips: list[str] = []
    # Aggregate Logic/Evidence/Rhetoric over the spoken transcript. NULL until
    # the background voice scorer finishes (a few seconds after the session ends).
    score_logic: Optional[float] = None
    score_evidence: Optional[float] = None
    score_rhetoric: Optional[float] = None


class TranscriptLineSavedOut(BaseModel):
    ok: bool
