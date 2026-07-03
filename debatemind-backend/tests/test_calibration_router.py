from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from debatemind.database import Base, get_db
from debatemind.deps import current_user_id
from debatemind.models.user import User
from debatemind.routers import calibration as calibration_router
from debatemind.services import calibration_svc


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def api_client(session_factory, monkeypatch):
    calibration_svc.reset("u1")
    monkeypatch.setattr(
        calibration_router,
        "extract_argument",
        AsyncMock(
            side_effect=lambda state: {
                **state,
                "extracted_pattern": "EvidenceBased",
                "extracted_fallacy": None,
                "evidence_quality": "Moderate",
            }
        ),
    )
    monkeypatch.setattr(calibration_router, "remember_argument_task", MagicMock())

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app = FastAPI()
    app.include_router(calibration_router.router, prefix="/api/calibration")
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[current_user_id] = lambda: "u1"
    return TestClient(app)


async def _make_user(session_factory, calibration_done=False):
    async with session_factory() as db:
        db.add(
            User(id="u1", email="u1@x.com", hashed_password="x", calibration_done=calibration_done)
        )
        await db.commit()


async def test_status_needed_true_with_first_topic(api_client, session_factory):
    await _make_user(session_factory)
    resp = api_client.get("/api/calibration/status")
    body = resp.json()["data"]
    assert body["needed"] is True
    assert body["index"] == 1
    assert body["total"] == 3


async def test_status_needed_false_when_already_done(api_client, session_factory):
    await _make_user(session_factory, calibration_done=True)
    resp = api_client.get("/api/calibration/status")
    assert resp.json()["data"]["needed"] is False


async def test_answer_advances_through_all_three_topics(api_client, session_factory):
    await _make_user(session_factory)

    r1 = api_client.post("/api/calibration/answer", json={"text": "a1"})
    assert r1.json()["data"]["done"] is False
    assert r1.json()["data"]["index"] == 2

    r2 = api_client.post("/api/calibration/answer", json={"text": "a2"})
    assert r2.json()["data"]["done"] is False
    assert r2.json()["data"]["index"] == 3

    r3 = api_client.post("/api/calibration/answer", json={"text": "a3"})
    assert r3.json()["data"]["done"] is True


async def test_answer_marks_user_calibration_done_in_db(api_client, session_factory):
    await _make_user(session_factory)
    for _ in range(3):
        api_client.post("/api/calibration/answer", json={"text": "a"})

    from sqlalchemy import select

    from debatemind.models.user import User as UserModel

    async with session_factory() as db:
        user = (await db.execute(select(UserModel).where(UserModel.id == "u1"))).scalar_one()
        assert user.calibration_done is True


async def test_answer_rejected_once_already_done(api_client, session_factory):
    await _make_user(session_factory, calibration_done=True)
    resp = api_client.post("/api/calibration/answer", json={"text": "a"})
    assert resp.status_code == 400
