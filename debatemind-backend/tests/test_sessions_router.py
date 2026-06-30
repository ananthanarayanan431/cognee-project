"""
API-level tests for the sessions router's concept/source-upload endpoints.
storage_svc (MinIO) and cognee_svc.index_source_document are mocked so no
real MinIO/Cognee I/O happens; the DB layer is a real in-memory SQLite,
same pattern as test_progress_svc.py.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from debatemind.database import Base, get_db
from debatemind.deps import current_user_id
from debatemind.models.session import DebateSession
from debatemind.routers import sessions as sessions_router
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
    body = resp.json()
    assert body["description"] == "Focus on EU AI Act"
    assert body["has_source"] is False


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


async def test_upload_source_indexes_pdf_and_persists_object_key(
    api_client, session_factory, monkeypatch, tmp_path
):
    session_id = await _make_session(session_factory)
    fake_local_path = tmp_path / "evidence.pdf"
    fake_local_path.write_bytes(b"local copy")
    object_key = f"sources/{session_id}/evidence.pdf"

    upload_mock = MagicMock(return_value=object_key)
    download_mock = MagicMock(return_value=fake_local_path)
    index_mock = AsyncMock()
    monkeypatch.setattr(storage_svc, "upload_source", upload_mock)
    monkeypatch.setattr(storage_svc, "download_to_tempfile", download_mock)
    monkeypatch.setattr(sessions_router, "index_source_document", index_mock)

    resp = api_client.post(
        f"/api/sessions/{session_id}/source",
        files={"file": ("evidence.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )

    assert resp.status_code == 200
    assert resp.json() == {"status": "indexed", "source_filename": "evidence.pdf"}
    upload_mock.assert_called_once_with(session_id, "evidence.pdf", b"%PDF-1.4 fake")
    index_mock.assert_awaited_once_with(session_id, str(fake_local_path))
    assert not fake_local_path.exists()

    async with session_factory() as db:
        result = await db.execute(select(DebateSession).where(DebateSession.id == session_id))
        session = result.scalar_one()
        assert session.source_object_key == object_key
        assert session.source_filename == "evidence.pdf"


async def test_upload_source_500s_and_leaves_session_ungrounded_when_indexing_fails(
    api_client, session_factory, monkeypatch, tmp_path
):
    session_id = await _make_session(session_factory)
    fake_local_path = tmp_path / "evidence.pdf"
    fake_local_path.write_bytes(b"local copy")

    monkeypatch.setattr(storage_svc, "upload_source", MagicMock(return_value="key"))
    monkeypatch.setattr(
        storage_svc, "download_to_tempfile", MagicMock(return_value=fake_local_path)
    )
    monkeypatch.setattr(
        sessions_router, "index_source_document", AsyncMock(side_effect=RuntimeError("cognee down"))
    )

    resp = api_client.post(
        f"/api/sessions/{session_id}/source",
        files={"file": ("evidence.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )

    assert resp.status_code == 500

    async with session_factory() as db:
        result = await db.execute(select(DebateSession).where(DebateSession.id == session_id))
        session = result.scalar_one()
        assert session.source_object_key is None


async def test_get_source_file_returns_presigned_url(api_client, session_factory, monkeypatch):
    session_id = await _make_session(
        session_factory, source_object_key="sources/x/e.pdf", source_filename="e.pdf"
    )
    monkeypatch.setattr(
        storage_svc, "get_source_url", MagicMock(return_value="https://minio.local/presigned")
    )

    resp = api_client.get(f"/api/sessions/{session_id}/source-file")

    assert resp.status_code == 200
    assert resp.json() == {"url": "https://minio.local/presigned"}


async def test_get_source_file_404s_when_no_source(api_client, session_factory):
    session_id = await _make_session(session_factory)

    resp = api_client.get(f"/api/sessions/{session_id}/source-file")

    assert resp.status_code == 404
