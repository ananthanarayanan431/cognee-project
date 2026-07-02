"""Shared constants, dataset-name builders, and log helpers for every cognee module."""

import time
from pathlib import Path

ADD_TIMEOUT = 60.0
COGNIFY_TIMEOUT = 300.0
SEARCH_TIMEOUT = 10.0

# Static, hand-authored domain ontology that guides cognee's graph extraction.
# Resolved from this module's location (not the process CWD) so it works the
# same whether run from source, a wheel, or the Docker image.
ONTOLOGY_PATH = Path(__file__).parent / "ontology" / "debate_domain.owl"


def ontology_file() -> str | None:
    """Absolute path to the debate ontology, or None if the asset is absent.

    Returning None makes cognee.cognify() behave exactly as before (it falls
    back to an empty ontology), so a missing file degrades gracefully in
    production instead of raising.
    """
    return str(ONTOLOGY_PATH) if ONTOLOGY_PATH.exists() else None


def fingerprint_dataset(user_id: str) -> str:
    return f"user_{user_id}_fingerprint"


def elapsed_ms(t0: float) -> int:
    return int((time.monotonic() - t0) * 1000)


def preview(text: str, limit: int = 200) -> str:
    return text[:limit] + ("…" if len(text) > limit else "")


def result_text(r) -> str:
    if isinstance(r, str):
        return r
    if isinstance(r, dict):
        return r.get("text", str(r))
    return getattr(r, "text", str(r))


def filter_out_patterns(items: list[dict], patterns: set[str] | None) -> list[dict]:
    """Drop recalled argument records whose ArgumentPattern is a mastered pattern.

    This is what makes forget()/mastery behaviourally real: once a pattern is
    mastered, its weakness records stop being fed to the opponent, so the AI
    demonstrably stops targeting it. Session-summary records are kept (they carry
    topic-level context, not a single exploitable pattern).
    """
    if not patterns:
        return items
    markers = tuple(f"ArgumentPattern: {p}" for p in patterns)
    return [it for it in items if not any(m in it.get("text", "") for m in markers)]
