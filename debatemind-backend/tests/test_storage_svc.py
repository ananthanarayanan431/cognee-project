"""
Unit tests for storage_svc — verifies the MinIO client is called with the
right bucket/object-key/content-type. The MinIO client itself is mocked via
_get_client(); no real MinIO I/O happens here.
"""

from datetime import timedelta
from unittest.mock import MagicMock

from debatemind.services import storage_svc


def test_upload_source_puts_object_under_session_scoped_key(monkeypatch):
    mock_client = MagicMock()
    monkeypatch.setattr(storage_svc, "_get_client", lambda: mock_client)

    object_key = storage_svc.upload_source("s1", "evidence.pdf", b"%PDF-1.4 fake content")

    assert object_key == "sources/s1/evidence.pdf"
    mock_client.put_object.assert_called_once()
    args, kwargs = mock_client.put_object.call_args
    assert args[0] == storage_svc.settings.minio_bucket
    assert args[1] == "sources/s1/evidence.pdf"
    assert kwargs["length"] == len(b"%PDF-1.4 fake content")
    assert kwargs["content_type"] == "application/pdf"


def test_upload_source_uses_only_the_basename_of_the_filename(monkeypatch):
    mock_client = MagicMock()
    monkeypatch.setattr(storage_svc, "_get_client", lambda: mock_client)

    object_key = storage_svc.upload_source("s1", "../../etc/evidence.pdf", b"data")

    assert object_key == "sources/s1/evidence.pdf"


def test_get_source_url_returns_a_presigned_url_with_seven_day_expiry(monkeypatch):
    mock_client = MagicMock()
    mock_client.presigned_get_object.return_value = "https://minio.local/presigned"
    monkeypatch.setattr(storage_svc, "_get_client", lambda: mock_client)

    url = storage_svc.get_source_url("sources/s1/evidence.pdf")

    assert url == "https://minio.local/presigned"
    mock_client.presigned_get_object.assert_called_once_with(
        storage_svc.settings.minio_bucket,
        "sources/s1/evidence.pdf",
        expires=timedelta(days=7),
    )


def test_download_to_tempfile_calls_fget_object_and_returns_a_pdf_path(monkeypatch):
    mock_client = MagicMock()
    monkeypatch.setattr(storage_svc, "_get_client", lambda: mock_client)

    result = storage_svc.download_to_tempfile("sources/s1/evidence.pdf")

    mock_client.fget_object.assert_called_once()
    call_args = mock_client.fget_object.call_args.args
    assert call_args[0] == storage_svc.settings.minio_bucket
    assert call_args[1] == "sources/s1/evidence.pdf"
    assert str(result) == call_args[2]
    assert result.suffix == ".pdf"


def test_ensure_bucket_creates_bucket_when_missing(monkeypatch):
    mock_client = MagicMock()
    mock_client.bucket_exists.return_value = False
    monkeypatch.setattr(storage_svc, "_get_client", lambda: mock_client)

    storage_svc.ensure_bucket()

    mock_client.make_bucket.assert_called_once_with(storage_svc.settings.minio_bucket)


def test_ensure_bucket_skips_creation_when_bucket_exists(monkeypatch):
    mock_client = MagicMock()
    mock_client.bucket_exists.return_value = True
    monkeypatch.setattr(storage_svc, "_get_client", lambda: mock_client)

    storage_svc.ensure_bucket()

    mock_client.make_bucket.assert_not_called()
