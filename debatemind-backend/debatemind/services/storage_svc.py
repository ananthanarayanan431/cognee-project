import os
import tempfile
from datetime import timedelta
from io import BytesIO
from pathlib import Path

from minio import Minio

from debatemind.config import settings

_client: Minio | None = None


def _get_client() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
    return _client


def ensure_bucket() -> None:
    client = _get_client()
    if not client.bucket_exists(settings.minio_bucket):
        client.make_bucket(settings.minio_bucket)


def upload_source(session_id: str, filename: str, data: bytes) -> str:
    safe_filename = Path(filename).name
    object_key = f"sources/{session_id}/{safe_filename}"
    client = _get_client()
    client.put_object(
        settings.minio_bucket,
        object_key,
        BytesIO(data),
        length=len(data),
        content_type="application/pdf",
    )
    return object_key


def get_source_url(object_key: str) -> str:
    client = _get_client()
    return client.presigned_get_object(settings.minio_bucket, object_key, expires=timedelta(days=7))


def download_to_tempfile(object_key: str) -> Path:
    client = _get_client()
    suffix = Path(object_key).suffix
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    client.fget_object(settings.minio_bucket, object_key, tmp_path)
    return Path(tmp_path)
