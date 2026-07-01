"""Public API for all cognee operations.

Import from here rather than the sub-modules so call sites stay stable
if the internal layout changes.

    from debatemind.cognee import remember_argument, recall_weaknesses
"""

from debatemind.cognee.fingerprint import (
    forget_pattern,
    improve_fingerprint,
    reactivate_pattern_fact,
    recall_weaknesses,
    remember_argument,
)

__all__ = [
    "remember_argument",
    "recall_weaknesses",
    "improve_fingerprint",
    "forget_pattern",
    "reactivate_pattern_fact",
]
