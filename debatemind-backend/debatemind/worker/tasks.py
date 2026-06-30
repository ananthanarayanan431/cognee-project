import asyncio
import logging

from celery.signals import worker_init
from sqlalchemy import update

from debatemind.database import AsyncSessionLocal
from debatemind.models.session import DebateSession
from debatemind.services import storage_svc
from debatemind.services.cognee_svc import index_source_document
from debatemind.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@worker_init.connect
def _configure_cognee(**kwargs):
    from debatemind.config import settings
    from debatemind.services.cognee_config import configure_cognee

    configure_cognee(settings)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=30)
def index_source_task(self, session_id: str, object_key: str) -> None:
    try:
        asyncio.run(_do_index(session_id, object_key))
    except Exception as exc:
        logger.exception("index_source_task failed for session %s", session_id)
        asyncio.run(_set_status(session_id, "failed"))
        raise self.retry(exc=exc)


async def _do_index(session_id: str, object_key: str) -> None:
    tmp_path = storage_svc.download_to_tempfile(object_key)
    try:
        await index_source_document(session_id, str(tmp_path))
    finally:
        tmp_path.unlink(missing_ok=True)
    await _set_status(session_id, "indexed")


async def _set_status(session_id: str, status: str) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(DebateSession).where(DebateSession.id == session_id).values(source_status=status)
        )
        await db.commit()
