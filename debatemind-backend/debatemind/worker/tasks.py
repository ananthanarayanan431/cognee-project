import asyncio
import logging

from celery.signals import worker_init

from debatemind.config import settings
from debatemind.worker.celery_app import celery_app  # noqa: F401 — ensures tasks are registered

logger = logging.getLogger(__name__)


@worker_init.connect
def _configure_cognee(**kwargs):
    import cognee

    from debatemind.services.cognee_config import configure_cognee

    configure_cognee(settings)
    asyncio.run(cognee.setup())
