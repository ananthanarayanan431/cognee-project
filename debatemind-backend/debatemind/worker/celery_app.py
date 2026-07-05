"""Celery app for cognee fingerprint writes (see debatemind/worker/tasks.py).

In production this must run as a second process from the same image, started
with `celery -A debatemind.worker.celery_app worker --concurrency=2` and the
same env vars as the API (REDIS_URL plus every COGNEE_*/OPENAI_*/OPENROUTER_*
var, since @worker_init.connect configures cognee independently per process).
"""

from celery import Celery

from debatemind.config import settings

celery_app = Celery(
    "debatemind",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["debatemind.worker.tasks"],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    # Recycle each child after one task: cognee's async DB engines bind to the
    # first event loop a child uses, so a reused child fails on its second task.
    worker_max_tasks_per_child=1,
)
