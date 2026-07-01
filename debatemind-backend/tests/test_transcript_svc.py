from datetime import datetime, timezone

from debatemind.schemas.session import TranscriptExchange, TranscriptOut
from debatemind.services.transcript_svc import format_transcript_text


def _transcript() -> TranscriptOut:
    return TranscriptOut(
        session_id="s1",
        topic="AI regulation should be government-led",
        difficulty="targeted",
        started_at=datetime(2026, 6, 28, 14, 0, 0, tzinfo=timezone.utc),
        exchanges=[
            TranscriptExchange(
                turn_number=1,
                user_message="Government bodies have decades of regulatory experience.",
                opponent_response="The EU Commission took 4 years to pass the AI Act.",
                judge_logic=4.0,
                judge_evidence=3.0,
                judge_rhetoric=7.0,
                fallacy="AppealToAuthority",
                outcome="Lost",
                created_at=datetime(2026, 6, 28, 14, 0, 14, tzinfo=timezone.utc),
            )
        ],
    )


def test_format_includes_topic_and_meta_line():
    text = format_transcript_text(_transcript())
    assert "AI regulation should be government-led" in text
    assert "Targeted" in text
    assert "1 exchanges" in text


def test_format_includes_both_speakers_and_judge_line():
    text = format_transcript_text(_transcript())
    assert "YOU" in text
    assert "Government bodies have decades" in text
    assert "OPPONENT" in text
    assert "EU Commission took 4 years" in text
    assert "AppealToAuthority detected" in text
    assert "Logic 4" in text and "Evidence 3" in text and "Rhetoric 7" in text


def test_format_omits_judge_line_when_no_scores():
    transcript = _transcript()
    transcript.exchanges[0].judge_logic = None
    transcript.exchanges[0].judge_evidence = None
    transcript.exchanges[0].judge_rhetoric = None
    text = format_transcript_text(transcript)
    assert "JUDGE" not in text
