"""
API-level tests for the sessions router.
Cognee and the debate pipeline are mocked; the DB layer is a real in-memory SQLite.
"""

import json
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from debatemind.database import Base, get_db
from debatemind.deps import current_user_id
from debatemind.models.session import DebateSession, Exchange
from debatemind.models.voice_session import VoiceSession
from debatemind.routers import sessions as sessions_router
from debatemind.schemas.graph import GraphNode, GraphOut


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def api_client(session_factory):
    async def override_get_db():
        async with session_factory() as session:
            yield session

    app = FastAPI()
    app.include_router(sessions_router.router, prefix="/api/sessions")
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[current_user_id] = lambda: "u1"
    return TestClient(app)


async def _make_session(session_factory, **overrides) -> str:
    async with session_factory() as db:
        overrides.setdefault("topic", "AI Safety")
        session = DebateSession(user_id="u1", **overrides)
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return session.id


def _parse_sse_events(body: str) -> list[dict]:
    events = []
    for line in body.splitlines():
        if not line.startswith("data: "):
            continue
        raw = line[len("data: ") :]
        if raw == "[DONE]":
            continue
        events.append(json.loads(raw))
    return events


async def test_send_message_streams_stage_events_then_response(
    api_client, session_factory, monkeypatch
):
    session_id = await _make_session(session_factory)

    node_updates = [
        (
            "extract",
            {
                "extracted_pattern": "EvidenceBased",
                "extracted_fallacy": None,
                "evidence_quality": "Moderate",
            },
        ),
        ("opponent", {"opponent_response": "Hello there"}),
        (
            "judge",
            {
                "judge_logic": 7.0,
                "judge_evidence": 6.0,
                "judge_rhetoric": 8.0,
                "judge_fallacy": None,
                "outcome": "Won",
            },
        ),
        ("mastery", {"mastery_events": [], "consecutive_wins": 1}),
        ("remember", {}),
    ]

    class FakePipeline:
        async def astream(self, initial_state, stream_mode="updates"):
            state = dict(initial_state)
            for node_name, delta in node_updates:
                state.update(delta)
                yield {node_name: dict(state)}

    monkeypatch.setattr(sessions_router, "debate_pipeline", FakePipeline())
    monkeypatch.setattr(
        sessions_router,
        "session_scoped_fingerprint",
        AsyncMock(return_value=GraphOut(nodes=[], edges=[])),
    )
    # AsyncSessionLocal in the streaming generator bypasses the get_db override,
    # so point it at the test factory and stub out the mastery DB write.
    monkeypatch.setattr(sessions_router, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(sessions_router, "record_mastery_events", AsyncMock())

    with api_client.stream(
        "POST", f"/api/sessions/{session_id}/message", json={"text": "AI is risky"}
    ) as resp:
        body = "".join(resp.iter_text())

    assert resp.status_code == 200
    events = _parse_sse_events(body)
    types = [e["type"] for e in events]
    assert types == ["stage", "stage", "token", "token", "stage", "stage", "judge", "graph"]
    assert [e["stage"] for e in events if e["type"] == "stage"] == [
        "extract",
        "opponent",
        "judge",
        "mastery",
    ]
    assert "".join(e["text"] for e in events if e["type"] == "token") == "Hello there"
    judge_event = next(e for e in events if e["type"] == "judge")
    assert judge_event["outcome"] == "Won"
    assert body.rstrip().endswith("data: [DONE]")

    async with session_factory() as db:
        result = await db.execute(select(Exchange).where(Exchange.session_id == session_id))
        exchange = result.scalar_one()
        assert exchange.opponent_response == "Hello there"
        assert exchange.outcome == "Won"


async def test_send_message_emits_error_event_and_skips_persistence_on_pipeline_failure(
    api_client, session_factory, monkeypatch
):
    session_id = await _make_session(session_factory)

    class FailingPipeline:
        async def astream(self, initial_state, stream_mode="updates"):
            yield {"extract": {**initial_state, "extracted_pattern": "EvidenceBased"}}
            raise RuntimeError("boom")

    monkeypatch.setattr(sessions_router, "debate_pipeline", FailingPipeline())

    with api_client.stream(
        "POST", f"/api/sessions/{session_id}/message", json={"text": "x"}
    ) as resp:
        body = "".join(resp.iter_text())

    events = _parse_sse_events(body)
    assert events[-1] == {
        "type": "error",
        "detail": "Something went wrong generating a response.",
    }
    assert "[DONE]" not in body

    async with session_factory() as db:
        result = await db.execute(select(Exchange).where(Exchange.session_id == session_id))
        assert result.scalar_one_or_none() is None


async def test_start_session_persists_description(api_client):
    resp = api_client.post(
        "/api/sessions/start",
        json={
            "topic": "AI Safety",
            "description": "Focus on EU AI Act",
            "difficulty": "targeted",
            "user_position": "against",
        },
    )

    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["description"] == "Focus on EU AI Act"


async def test_end_session_dispatches_finalize_fingerprint_task(
    api_client, session_factory, monkeypatch
):
    session_id = await _make_session(session_factory)

    fake_task = Mock()
    monkeypatch.setattr(sessions_router, "finalize_session_fingerprint_task", fake_task)

    resp = api_client.post(f"/api/sessions/{session_id}/end")

    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "ended"
    fake_task.delay.assert_called_once_with("u1", session_id)


async def test_end_session_is_idempotent(api_client, session_factory, monkeypatch):
    """The frontend hits /end from three paths (button, Back nav, unload beacon),
    so ending an already-ended session must not re-run finalization: no duplicate
    session-summary node, no redundant cognify re-index."""
    session_id = await _make_session(session_factory)

    fake_task = Mock()
    monkeypatch.setattr(sessions_router, "finalize_session_fingerprint_task", fake_task)

    first = api_client.post(f"/api/sessions/{session_id}/end")
    second = api_client.post(f"/api/sessions/{session_id}/end")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["data"]["status"] == "ended"
    fake_task.delay.assert_called_once_with("u1", session_id)


async def test_end_session_dispatches_session_scoring(api_client, session_factory, monkeypatch):
    session_id = await _make_session(session_factory)

    monkeypatch.setattr(sessions_router, "finalize_session_fingerprint_task", Mock())
    score_mock = AsyncMock()
    monkeypatch.setattr(sessions_router, "score_session_background", score_mock)

    resp = api_client.post(f"/api/sessions/{session_id}/end")

    assert resp.status_code == 200
    score_mock.assert_called_once_with("u1", session_id)


async def test_list_sessions_backfills_score_for_ended_unscored_sessions(
    api_client, session_factory, monkeypatch
):
    """Sessions ended before session-level scoring existed show score 0 — the
    list endpoint should dispatch a background judge for exactly those with
    exchanges to score."""
    unscored_id = await _make_session(session_factory, status="ended")
    scored_id = await _make_session(session_factory, status="ended", overall_score=7.5)
    active_id = await _make_session(session_factory)  # active: not backfilled
    empty_ended_id = await _make_session(session_factory, status="ended")  # 0 turns

    async with session_factory() as db:
        for sid in (unscored_id, scored_id, active_id):
            db.add(Exchange(session_id=sid, turn_number=1, user_message="m"))
        await db.commit()

    score_mock = AsyncMock()
    monkeypatch.setattr(sessions_router, "score_session_background", score_mock)

    resp = api_client.get("/api/sessions")

    assert resp.status_code == 200
    assert empty_ended_id  # present in listing but never scored
    score_mock.assert_called_once_with("u1", unscored_id)


async def test_list_sessions_flags_has_voice_session(api_client, session_factory):
    voice_session_id = await _make_session(session_factory, topic="Voice Topic")
    text_session_id = await _make_session(session_factory, topic="Text Topic")

    async with session_factory() as db:
        db.add(VoiceSession(debate_session_id=voice_session_id, user_id="u1"))
        await db.commit()

    response = api_client.get("/api/sessions")
    assert response.status_code == 200

    items = {item["session_id"]: item for item in response.json()["data"]}
    assert items[voice_session_id]["has_voice_session"] is True
    assert items[text_session_id]["has_voice_session"] is False


async def test_get_graph_calls_session_scoped_fingerprint_with_session_and_topic(
    api_client, session_factory, monkeypatch
):
    session_id = await _make_session(session_factory, topic="AI Safety")
    fake_result = GraphOut(
        nodes=[GraphNode(id="topic", label="AI Safety", type="topic", weight=1.0)],
        edges=[],
    )
    mock_fingerprint = AsyncMock(return_value=fake_result)
    monkeypatch.setattr(sessions_router, "session_scoped_fingerprint", mock_fingerprint)

    resp = api_client.get(f"/api/sessions/{session_id}/graph")

    assert resp.status_code == 200
    assert resp.json()["data"]["nodes"][0]["id"] == "topic"
    mock_fingerprint.assert_awaited_once_with("u1", session_id, "AI Safety")


async def test_get_graph_404s_for_another_users_session(api_client, session_factory):
    async with session_factory() as db:
        other = DebateSession(user_id="u2", topic="Other")
        db.add(other)
        await db.commit()
        await db.refresh(other)
        other_id = other.id

    resp = api_client.get(f"/api/sessions/{other_id}/graph")

    assert resp.status_code == 404
