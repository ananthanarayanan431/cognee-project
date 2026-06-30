"""
API-level tests for the sessions router's concept/source-upload endpoints.
storage_svc (MinIO) and Celery tasks are mocked so no real MinIO/Cognee/Redis
I/O happens; the DB layer is a real in-memory SQLite.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from debatemind.database import Base, get_db
from debatemind.deps import current_user_id
from debatemind.models.session import DebateSession, Exchange
from debatemind.routers import sessions as sessions_router
from debatemind.schemas.graph import GraphOut
from debatemind.services import storage_svc


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
        session = DebateSession(user_id="u1", topic="AI Safety", **overrides)
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
        sessions_router, "build_graph", AsyncMock(return_value=GraphOut(nodes=[], edges=[]))
    )

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


async def test_start_session_persists_description_and_returns_has_source_false(api_client):
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
    assert body["has_source"] is False
    assert body["source_status"] == "none"


async def test_upload_source_rejects_non_pdf(api_client, session_factory):
    session_id = await _make_session(session_factory)

    resp = api_client.post(
        f"/api/sessions/{session_id}/source",
        files={"file": ("notes.txt", b"plain text", "text/plain")},
    )

    assert resp.status_code == 400


async def test_upload_source_rejects_oversized_file(api_client, session_factory, monkeypatch):
    session_id = await _make_session(session_factory)
    monkeypatch.setattr(sessions_router, "MAX_SOURCE_BYTES", 10)

    resp = api_client.post(
        f"/api/sessions/{session_id}/source",
        files={"file": ("evidence.pdf", b"x" * 100, "application/pdf")},
    )

    assert resp.status_code == 413


async def test_upload_source_enqueues_task_sets_pending_and_returns_202(
    api_client, session_factory, monkeypatch
):
    session_id = await _make_session(session_factory)
    object_key = f"sources/{session_id}/evidence.pdf"

    upload_mock = MagicMock(return_value=object_key)
    delay_mock = MagicMock()
    monkeypatch.setattr(storage_svc, "upload_source", upload_mock)
    monkeypatch.setattr(sessions_router.index_source_task, "delay", delay_mock)

    resp = api_client.post(
        f"/api/sessions/{session_id}/source",
        files={"file": ("evidence.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )

    assert resp.status_code == 202
    body = resp.json()["data"]
    assert body["status"] == "pending"
    assert body["source_filename"] == "evidence.pdf"

    delay_mock.assert_called_once_with(session_id, object_key)

    async with session_factory() as db:
        result = await db.execute(select(DebateSession).where(DebateSession.id == session_id))
        session = result.scalar_one()
        assert session.source_status == "pending"
        assert session.source_filename == "evidence.pdf"
        assert session.source_object_key == object_key


async def test_get_source_status_returns_current_status(api_client, session_factory):
    session_id = await _make_session(
        session_factory,
        source_status="indexed",
        source_object_key="sources/x/e.pdf",
        source_filename="e.pdf",
    )

    resp = api_client.get(f"/api/sessions/{session_id}/source-status")

    assert resp.status_code == 200
    assert resp.json()["data"] == {"source_status": "indexed"}


async def test_get_source_status_defaults_to_none_for_new_session(api_client, session_factory):
    session_id = await _make_session(session_factory)

    resp = api_client.get(f"/api/sessions/{session_id}/source-status")

    assert resp.status_code == 200
    assert resp.json()["data"] == {"source_status": "none"}


async def test_get_source_file_returns_presigned_url(api_client, session_factory, monkeypatch):
    session_id = await _make_session(
        session_factory, source_object_key="sources/x/e.pdf", source_filename="e.pdf"
    )
    monkeypatch.setattr(
        storage_svc, "get_source_url", MagicMock(return_value="https://minio.local/presigned")
    )

    resp = api_client.get(f"/api/sessions/{session_id}/source-file")

    assert resp.status_code == 200
    assert resp.json()["data"] == {"url": "https://minio.local/presigned"}


async def test_get_source_file_404s_when_no_source(api_client, session_factory):
    session_id = await _make_session(session_factory)

    resp = api_client.get(f"/api/sessions/{session_id}/source-file")

    assert resp.status_code == 404
