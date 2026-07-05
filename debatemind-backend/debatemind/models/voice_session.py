import uuid

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from debatemind.database import Base


class VoiceSession(Base):
    """One voice (WebRTC) session tied to a parent text DebateSession."""

    __tablename__ = "voice_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    debate_session_id: Mapped[str] = mapped_column(String, ForeignKey("sessions.id"), index=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    # id returned by OpenAI in the client_secrets response (sess_...)
    openai_session_id: Mapped[str] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="active")  # active | ended
    started_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=True)
    # Populated by `end_voice_session` tool
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=True)
    closing_summary: Mapped[str] = mapped_column(Text, nullable=True)
    # Logic/Evidence/Rhetoric over the spoken transcript; NULL until the
    # background scorer fills them after the session ends.
    score_logic: Mapped[float] = mapped_column(Float, nullable=True)
    score_evidence: Mapped[float] = mapped_column(Float, nullable=True)
    score_rhetoric: Mapped[float] = mapped_column(Float, nullable=True)
    # Watermark: user turns already classified into fingerprint patterns. Keeps
    # the live per-turn pass and the end-of-session sweep from double-counting.
    patterns_derived_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0
    )
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VoiceSessionNote(Base):
    """
    An AI-generated observation recorded during a voice debate via the
    `save_debate_observation` tool. Used for post-session coaching review.
    """

    __tablename__ = "voice_session_notes"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    voice_session_id: Mapped[str] = mapped_column(
        String, ForeignKey("voice_sessions.id"), index=True
    )
    # observation | fallacy | strong_argument | concession | position_flip
    #   | transcript_user | transcript_ai
    note_type: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    # For transcript_user notes: the argument pattern this turn was classified
    # as — the fingerprint's fast path (mirrors Exchange.detected_pattern).
    detected_pattern: Mapped[str] = mapped_column(String, nullable=True)
    outcome: Mapped[str] = mapped_column(String, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
