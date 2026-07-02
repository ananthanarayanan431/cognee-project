import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from debatemind.database import Base, get_db
from debatemind.models.user import User
from debatemind.routers import auth as auth_router
from debatemind.services.auth import hash_password


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
    app.include_router(auth_router.router, prefix="/api/auth")
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


async def test_register_returns_calibration_done_false(api_client):
    resp = api_client.post(
        "/api/auth/register", json={"email": "new@x.com", "password": "pw123456"}
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["calibration_done"] is False


async def test_login_returns_existing_calibration_state(api_client, session_factory):
    async with session_factory() as db:
        db.add(
            User(
                email="done@x.com",
                hashed_password=hash_password("pw123456"),
                calibration_done=True,
            )
        )
        await db.commit()

    resp = api_client.post("/api/auth/login", json={"email": "done@x.com", "password": "pw123456"})
    assert resp.status_code == 200
    assert resp.json()["data"]["calibration_done"] is True
