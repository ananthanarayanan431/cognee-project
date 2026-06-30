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
)
