"""Public API for all cognee operations.

Import from here rather than the sub-modules so call sites stay stable
if the internal layout changes.

    from debatemind.cognee import remember_argument, recall_weaknesses
"""

from debatemind.cognee.fingerprint import (
    improve_fingerprint,
    remember_argument,
    remember_personal_fact,
    remember_session_summary,
)
from debatemind.cognee.forget import forget_pattern, forget_personal_fact
from debatemind.cognee.recall import (
    cognitive_profile_text,
    filter_profile_patterns,
    recall_cognitive_profile,
    recall_topic_weaknesses,
    recall_user_facts,
    recall_weaknesses,
)

__all__ = [
    "remember_argument",
    "remember_session_summary",
    "remember_personal_fact",
    "recall_weaknesses",
    "recall_topic_weaknesses",
    "recall_user_facts",
    "recall_cognitive_profile",
    "filter_profile_patterns",
    "cognitive_profile_text",
    "improve_fingerprint",
    "forget_pattern",
    "forget_personal_fact",
]
