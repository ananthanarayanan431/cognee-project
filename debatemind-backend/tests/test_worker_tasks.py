"""
Unit tests for the Celery indexing task.
All async helpers (_do_index, _set_status) are tested directly without
going through the Celery machinery so we don't need a running broker.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from debatemind.worker import tasks as worker_tasks


async def test_do_index_downloads_indexes_and_sets_status_indexed(monkeypatch, tmp_path):
    fake_tmp = tmp_path / "e.pdf"
    fake_tmp.write_bytes(b"pdf data")

    download_mock = MagicMock(return_value=fake_tmp)
    index_mock = AsyncMock()
    set_status_mock = AsyncMock()

    monkeypatch.setattr(worker_tasks.storage_svc, "download_to_tempfile", download_mock)
    monkeypatch.setattr(worker_tasks, "index_source_document", index_mock)
    monkeypatch.setattr(worker_tasks, "_set_status", set_status_mock)

    await worker_tasks._do_index("s1", "sources/s1/e.pdf")

    download_mock.assert_called_once_with("sources/s1/e.pdf")
    index_mock.assert_awaited_once_with("s1", str(fake_tmp))
    set_status_mock.assert_awaited_once_with("s1", "indexed")
    assert not fake_tmp.exists()


async def test_do_index_cleans_up_tempfile_even_when_indexing_fails(monkeypatch, tmp_path):
    fake_tmp = tmp_path / "e.pdf"
    fake_tmp.write_bytes(b"pdf data")

    monkeypatch.setattr(
        worker_tasks.storage_svc, "download_to_tempfile", MagicMock(return_value=fake_tmp)
    )
    monkeypatch.setattr(
        worker_tasks, "index_source_document", AsyncMock(side_effect=RuntimeError("cognee down"))
    )
    monkeypatch.setattr(worker_tasks, "_set_status", AsyncMock())

    with pytest.raises(RuntimeError, match="cognee down"):
        await worker_tasks._do_index("s1", "sources/s1/e.pdf")

    assert not fake_tmp.exists()


async def test_set_status_updates_db(monkeypatch, tmp_path):
    from unittest.mock import AsyncMock, MagicMock

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from debatemind.database import Base
    from debatemind.models.session import DebateSession

    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    test_engine = create_async_engine(db_url)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    test_factory = async_sessionmaker(test_engine, expire_on_commit=False)

    async with test_factory() as db:
        session = DebateSession(user_id="u1", topic="AI", source_status="pending")
        db.add(session)
        await db.commit()
        session_id = session.id

    # Return a no-op mock engine (keep test_engine alive) + the real test factory
    mock_engine = MagicMock()
    mock_engine.dispose = AsyncMock()
    monkeypatch.setattr(worker_tasks, "_make_db_factory", lambda: (mock_engine, test_factory))

    await worker_tasks._set_status(session_id, "indexed")

    async with test_factory() as db:
        result = await db.execute(select(DebateSession).where(DebateSession.id == session_id))
        s = result.scalar_one()
        assert s.source_status == "indexed"

    await test_engine.dispose()
