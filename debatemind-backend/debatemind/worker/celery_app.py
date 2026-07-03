"""Celery app for cognee fingerprint writes (see debatemind/worker/tasks.py).

Locally, `make dev` / `make start` already runs this worker alongside the API
(see the Makefile's `celery`/`dev`/`start` targets) — no extra setup needed.

For a cloud deployment: this worker must run as a SECOND process from the
same image as the API (the Dockerfile needs no changes — celery[redis] is
already an installed dependency). Point the platform's second service/process
at the same image with this start command instead of the API's default CMD:

    celery -A debatemind.worker.celery_app worker --loglevel=info --concurrency=2

Give it the same environment variables as the API service — in particular
REDIS_URL (the broker/backend, must point at the same Redis both processes
share) and every COGNEE_*/OPENAI_*/OPENROUTER_* variable configure_cognee()
reads, since @worker_init.connect below configures cognee independently in
this process, never sharing state with the API process's cognee engine.
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
)
