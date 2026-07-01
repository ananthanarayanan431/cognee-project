"""Shared constants, dataset-name builders, and log helpers for every cognee module."""

import time

ADD_TIMEOUT = 60.0
COGNIFY_TIMEOUT = 300.0
SEARCH_TIMEOUT = 10.0


def fingerprint_dataset(user_id: str) -> str:
    return f"user_{user_id}_fingerprint"


def source_dataset(session_id: str) -> str:
    return f"session_{session_id}_source"


def elapsed_ms(t0: float) -> int:
    return int((time.monotonic() - t0) * 1000)


def preview(text: str, limit: int = 200) -> str:
    return text[:limit] + ("…" if len(text) > limit else "")


def result_text(r) -> str:
    return r if isinstance(r, str) else getattr(r, "text", str(r))
