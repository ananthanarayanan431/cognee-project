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
    # Aggregate Logic/Evidence/Rhetoric read over the spoken transcript, written
    # by services/voice_score_svc.py after the session ends. Voice runs no
    # per-turn judge, so these stay NULL until the background scorer fills them.
    score_logic: Mapped[float] = mapped_column(Float, nullable=True)
    score_evidence: Mapped[float] = mapped_column(Float, nullable=True)
    score_rhetoric: Mapped[float] = mapped_column(Float, nullable=True)
    # How many of this session's user turns have already been classified into
    # Cognitive Fingerprint patterns. The fingerprint builds live as the user
    # speaks: each transcript turn triggers derive_voice_session_patterns, which
    # only processes turns past this watermark, and the end-of-session dispatch
    # sweeps up whatever tail arrived too late for a live pass. Keeps the live
    # per-turn pass and the end pass from double-counting the same turn.
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
    note_type: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
