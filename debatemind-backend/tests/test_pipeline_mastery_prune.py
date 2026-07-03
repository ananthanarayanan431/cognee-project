"""
Regression test for _mastery_prune_node: the same `mastery_events` state key
that check_mastery() populates with newly-achieved patterns is read downstream
by routers/sessions.py to persist MasteryLog rows and to notify the frontend
("mastery": [...] in the judge payload). _mastery_prune_node must not repurpose
that key to mean "patterns whose forget_pattern dispatch failed" — doing so
erases the achieved-mastery signal on the (common) success path.
"""

from unittest.mock import MagicMock, patch

from debatemind.agents import pipeline


async def test_successful_forget_pattern_dispatch_preserves_mastery_events():
    state = {"user_id": "u1", "mastery_events": ["AdHominem"]}
    mock_task = MagicMock()

    with patch.object(pipeline, "forget_pattern_task", mock_task):
        result = await pipeline._mastery_prune_node(state)

    mock_task.delay.assert_called_once_with("u1", "AdHominem")
    assert result["mastery_events"] == ["AdHominem"]


async def test_failed_forget_pattern_dispatch_still_preserves_mastery_events():
    """A dispatch failure (e.g. Redis unreachable) must not gate Postgres persistence.

    MasteryLog (the source of truth used by get_active_mastered_patterns) is
    written from this same list downstream — mirroring voice_agent/tools.py,
    which writes MasteryLog unconditionally regardless of the dispatched
    forget_pattern task's outcome.
    """
    state = {"user_id": "u1", "mastery_events": ["AdHominem"]}
    mock_task = MagicMock()
    mock_task.delay.side_effect = RuntimeError("boom")

    with patch.object(pipeline, "forget_pattern_task", mock_task):
        result = await pipeline._mastery_prune_node(state)

    assert result["mastery_events"] == ["AdHominem"]
