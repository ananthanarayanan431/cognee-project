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


async def test_failed_remember_argument_dispatch_does_not_raise():
    """A Celery `.delay()` call connects to the broker synchronously and can

    raise immediately if Redis is unreachable. That must not crash the
    debate-turn request — _remember_node should degrade gracefully, same as
    _mastery_prune_node's forget_pattern dispatch does.
    """
    state = {
        "user_id": "u1",
        "session_id": "s1",
        "topic": "t1",
        "user_message": "some argument",
        "judge_logic": 0.5,
        "judge_evidence": 0.5,
        "judge_rhetoric": 0.5,
    }
    mock_task = MagicMock()
    mock_task.delay.side_effect = RuntimeError("boom")

    with patch.object(pipeline, "remember_argument_task", mock_task):
        result = await pipeline._remember_node(state)

    mock_task.delay.assert_called_once()
    assert result is state


async def test_failed_remember_personal_fact_dispatch_does_not_raise():
    """Same resilience requirement as remember_argument, but for the per-fact

    loop in _remember_facts_node — one fact's dispatch failure must not stop
    the remaining facts in the batch from being dispatched.
    """
    state = {"user_id": "u1", "session_id": "s1", "personal_facts": ["fact one", "fact two"]}
    mock_task = MagicMock()
    mock_task.delay.side_effect = RuntimeError("boom")

    async def fake_record_user_facts(db, user_id, session_id, facts):
        return facts

    with (
        patch.object(pipeline, "remember_personal_fact_task", mock_task),
        patch.object(pipeline, "record_user_facts", fake_record_user_facts),
        patch.object(pipeline, "AsyncSessionLocal") as mock_session_local,
    ):
        mock_session_local.return_value.__aenter__.return_value = MagicMock()
        mock_session_local.return_value.__aexit__.return_value = False
        result = await pipeline._remember_facts_node(state)

    assert mock_task.delay.call_count == 2
    assert result is state
