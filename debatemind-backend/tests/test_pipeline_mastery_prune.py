"""
Regression test for _mastery_prune_node: the same `mastery_events` state key
that check_mastery() populates with newly-achieved patterns is read downstream
by routers/sessions.py to persist MasteryLog rows and to notify the frontend
("mastery": [...] in the judge payload). _mastery_prune_node must not repurpose
that key to mean "patterns whose forget_pattern() write failed" — doing so
erases the achieved-mastery signal on the (common) success path.
"""

from unittest.mock import AsyncMock, patch

from debatemind.agents import pipeline


async def test_successful_forget_pattern_preserves_mastery_events():
    state = {"user_id": "u1", "mastery_events": ["AdHominem"]}

    with patch.object(pipeline, "forget_pattern", new=AsyncMock(return_value=None)):
        result = await pipeline._mastery_prune_node(state)

    assert result["mastery_events"] == ["AdHominem"]


async def test_failed_forget_pattern_still_preserves_mastery_events():
    """A best-effort Cognee write failure must not gate Postgres persistence.

    MasteryLog (the source of truth used by get_active_mastered_patterns) is
    written from this same list downstream — mirroring voice_agent/tools.py,
    which writes MasteryLog unconditionally regardless of the Cognee task's
    outcome (see the fire-and-forget forget_pattern task there).
    """
    state = {"user_id": "u1", "mastery_events": ["AdHominem"]}

    with patch.object(pipeline, "forget_pattern", new=AsyncMock(side_effect=RuntimeError("boom"))):
        result = await pipeline._mastery_prune_node(state)

    assert result["mastery_events"] == ["AdHominem"]
