from debatemind.schemas.session import TranscriptOut


def format_transcript_text(transcript: TranscriptOut) -> str:
    lines = [
        transcript.topic,
        f"{transcript.difficulty.capitalize()} · {transcript.started_at:%B %d, %Y} · "
        f"{len(transcript.exchanges)} exchanges",
        "=" * 60,
        "",
    ]
    for ex in transcript.exchanges:
        lines.append(f"YOU — {ex.created_at:%H:%M:%S}")
        lines.append(ex.user_message)
        lines.append("")

        fallacy_note = f"  [{ex.fallacy} detected]" if ex.fallacy else ""
        lines.append(f"OPPONENT — {ex.created_at:%H:%M:%S}{fallacy_note}")
        lines.append(ex.opponent_response)
        lines.append("")

        if (
            ex.judge_logic is not None
            and ex.judge_evidence is not None
            and ex.judge_rhetoric is not None
        ):
            lines.append(
                f"JUDGE   Logic {ex.judge_logic:g} · Evidence {ex.judge_evidence:g} · "
                f"Rhetoric {ex.judge_rhetoric:g}"
            )
        lines.append("-" * 60)
        lines.append("")
    return "\n".join(lines)
