"""Tests for app/documents/storage.py's S3StorageProvider (deployment
readiness pass) and get_storage_provider()'s config-based selection. Uses
moto's mock_aws to fake the S3 API in-process - no real AWS credentials, no
real network calls, no MinIO/Docker dependency, same reasoning as
FakeClient in tests/test_gemini_provider.py for the AI providers: this
exercises the real boto3 call shapes (Bucket/Key/Body/ContentType kwargs),
just against a fake backend instead of a real one.
"""
import io

import boto3
import pytest
from moto import mock_aws

from app.documents.storage import (
    LocalStorageProvider,
    S3StorageProvider,
    UnsupportedFileError,
    get_storage_provider,
)

BUCKET = "ausvia-test-bucket"
VALID_PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>"


class FakeFileStorage:
    """Minimal stand-in for werkzeug's FileStorage - matches what
    _validate_and_sniff/upload() actually touch (filename, stream)."""

    def __init__(self, data, filename):
        self.filename = filename
        self.stream = io.BytesIO(data)

    def save(self, path):
        with open(path, "wb") as f:
            f.write(self.stream.read())


@pytest.fixture
def s3_provider():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield S3StorageProvider(bucket=BUCKET, client=client)


def test_upload_stores_object_and_returns_expected_metadata(s3_provider):
    file_storage = FakeFileStorage(VALID_PDF, "cv.pdf")
    stored_filename, storage_path, file_size, mime_type = s3_provider.upload(file_storage, subdir="42")

    assert storage_path == f"42/{stored_filename}"
    assert mime_type == "application/pdf"
    assert file_size == len(VALID_PDF)

    obj = s3_provider._client.get_object(Bucket=BUCKET, Key=storage_path)
    assert obj["Body"].read() == VALID_PDF
    assert obj["ContentType"] == "application/pdf"


def test_upload_rejects_content_that_does_not_match_extension(s3_provider):
    file_storage = FakeFileStorage(b"not a real pdf", "fake.pdf")
    with pytest.raises(UnsupportedFileError, match="doesn't match"):
        s3_provider.upload(file_storage, subdir="42")


def test_full_path_downloads_object_to_a_real_local_file(s3_provider):
    file_storage = FakeFileStorage(VALID_PDF, "cv.pdf")
    _, storage_path, _, _ = s3_provider.upload(file_storage, subdir="42")

    local_path = s3_provider.full_path(storage_path)
    with open(local_path, "rb") as f:
        assert f.read() == VALID_PDF


def test_full_path_raises_file_not_found_for_a_missing_key(s3_provider):
    with pytest.raises(FileNotFoundError):
        s3_provider.full_path("42/does-not-exist.pdf")


def test_delete_removes_the_object(s3_provider):
    file_storage = FakeFileStorage(VALID_PDF, "cv.pdf")
    _, storage_path, _, _ = s3_provider.upload(file_storage, subdir="42")

    s3_provider.delete(storage_path)
    with pytest.raises(FileNotFoundError):
        s3_provider.full_path(storage_path)


def test_delete_is_a_silent_no_op_for_a_missing_key(s3_provider):
    # Matches LocalStorageProvider.delete's behavior: deleting something
    # that's already gone is not an error.
    s3_provider.delete("42/never-existed.pdf")


def test_prefix_is_applied_to_the_underlying_s3_key_but_not_the_returned_storage_path():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        provider = S3StorageProvider(bucket=BUCKET, prefix="prod", client=client)

        file_storage = FakeFileStorage(VALID_PDF, "cv.pdf")
        _, storage_path, _, _ = provider.upload(file_storage, subdir="42")

        assert not storage_path.startswith("prod/")
        # the real object lives under the prefix in the bucket...
        client.get_object(Bucket=BUCKET, Key=f"prod/{storage_path}")
        # ...and full_path() transparently resolves it back through the prefix.
        local_path = provider.full_path(storage_path)
        with open(local_path, "rb") as f:
            assert f.read() == VALID_PDF


def test_get_storage_provider_defaults_to_local():
    config = {"STORAGE_PROVIDER": "local", "UPLOAD_DIR": "/tmp/uploads"}
    provider = get_storage_provider(config)
    assert isinstance(provider, LocalStorageProvider)
    assert provider.base_dir == "/tmp/uploads"


def test_get_storage_provider_returns_local_when_unset():
    provider = get_storage_provider({"UPLOAD_DIR": "/tmp/uploads"})
    assert isinstance(provider, LocalStorageProvider)


def test_get_storage_provider_returns_s3_when_configured():
    config = {
        "STORAGE_PROVIDER": "s3",
        "S3_BUCKET": BUCKET,
        "S3_PREFIX": "prod",
        "S3_REGION": "eu-central-1",
        "S3_ENDPOINT_URL": None,
        "S3_ACCESS_KEY_ID": None,
        "S3_SECRET_ACCESS_KEY": None,
    }
    provider = get_storage_provider(config)
    assert isinstance(provider, S3StorageProvider)
    assert provider.bucket == BUCKET
    assert provider.prefix == "prod"
