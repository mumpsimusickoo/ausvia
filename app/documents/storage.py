"""
StorageProvider abstraction (spec section 42). LocalStorageProvider writes to
local disk (dev/test default); S3StorageProvider (deployment readiness pass)
persists to any S3-compatible object store (AWS S3, a PaaS host's own object
storage, MinIO, etc.) instead, so uploaded documents survive a redeploy on
hosts that wipe local disk. Selected via get_storage_provider() / the
STORAGE_PROVIDER config var - callers never instantiate a provider directly.
"""
import os
import tempfile
import uuid
from abc import ABC, abstractmethod

from flask_babel import gettext as _
from werkzeug.utils import secure_filename

# extension -> (mime type, magic-byte signatures to verify against the real
# file content, since a renamed .exe with a .pdf extension must still be rejected)
ALLOWED_TYPES = {
    "pdf": ("application/pdf", [b"%PDF"]),
    "jpg": ("image/jpeg", [b"\xff\xd8\xff"]),
    "jpeg": ("image/jpeg", [b"\xff\xd8\xff"]),
    "png": ("image/png", [b"\x89PNG\r\n\x1a\n"]),
}
MAX_FILE_SIZE = 15 * 1024 * 1024  # 15 MB


class UnsupportedFileError(ValueError):
    pass


class StorageProvider(ABC):
    @abstractmethod
    def upload(self, file_storage, subdir):
        """Returns (stored_filename, storage_path, file_size, mime_type)."""

    @abstractmethod
    def delete(self, storage_path):
        ...

    @abstractmethod
    def full_path(self, storage_path):
        ...


def _validate_and_sniff(file_storage):
    original_name = secure_filename(file_storage.filename or "")
    ext = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
    if ext not in ALLOWED_TYPES:
        raise UnsupportedFileError(
            _(
                "Unsupported file type '.%(ext)s'. Allowed: %(allowed)s.",
                ext=ext, allowed=", ".join(sorted(ALLOWED_TYPES)),
            )
        )

    header = file_storage.stream.read(16)
    file_storage.stream.seek(0)
    mime_type, signatures = ALLOWED_TYPES[ext]
    if not any(header.startswith(sig) for sig in signatures):
        raise UnsupportedFileError(
            _("File content doesn't match its extension. The file may be corrupted or mislabeled.")
        )

    return ext, mime_type


class LocalStorageProvider(StorageProvider):
    def __init__(self, base_dir):
        self.base_dir = base_dir

    def upload(self, file_storage, subdir):
        ext, mime_type = _validate_and_sniff(file_storage)

        target_dir = os.path.join(self.base_dir, subdir)
        os.makedirs(target_dir, exist_ok=True)

        stored_filename = f"{uuid.uuid4().hex}.{ext}"
        storage_path = os.path.join(subdir, stored_filename)
        abs_path = os.path.join(self.base_dir, storage_path)

        file_storage.save(abs_path)
        file_size = os.path.getsize(abs_path)

        if file_size > MAX_FILE_SIZE:
            os.remove(abs_path)
            raise UnsupportedFileError(_("File exceeds the 15 MB size limit."))

        return stored_filename, storage_path, file_size, mime_type

    def delete(self, storage_path):
        abs_path = self.full_path(storage_path)
        if os.path.exists(abs_path):
            os.remove(abs_path)

    def full_path(self, storage_path):
        # normpath + startswith check blocks path traversal via a crafted storage_path
        candidate = os.path.normpath(os.path.join(self.base_dir, storage_path))
        if not candidate.startswith(os.path.normpath(self.base_dir)):
            raise ValueError("Invalid storage path.")
        return candidate


class S3StorageProvider(StorageProvider):
    """Same interface and behavior contract as LocalStorageProvider, backed
    by an S3-compatible bucket instead of local disk. `client` is injectable
    for tests (moto) - production code always leaves it as None and lets
    boto3 build a real client from the constructor args / its own default
    credential chain (env vars, IAM role, etc. - access_key_id/secret_access_key
    are optional for exactly this reason)."""

    def __init__(
        self, bucket, prefix="", region_name=None, endpoint_url=None,
        access_key_id=None, secret_access_key=None, client=None,
    ):
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        if client is not None:
            self._client = client
        else:
            import boto3

            self._client = boto3.client(
                "s3",
                region_name=region_name,
                endpoint_url=endpoint_url or None,
                aws_access_key_id=access_key_id or None,
                aws_secret_access_key=secret_access_key or None,
            )

    def _key(self, storage_path):
        # S3 keys always use "/", regardless of the host OS - storage_path
        # itself is already built with "/" below, this just guards against
        # a caller passing one through os.path.join on Windows (backslashes).
        return "/".join([self.prefix, storage_path]).strip("/") if self.prefix else storage_path

    def upload(self, file_storage, subdir):
        ext, mime_type = _validate_and_sniff(file_storage)

        data = file_storage.stream.read()
        file_storage.stream.seek(0)
        if len(data) > MAX_FILE_SIZE:
            raise UnsupportedFileError(_("File exceeds the 15 MB size limit."))

        stored_filename = f"{uuid.uuid4().hex}.{ext}"
        storage_path = f"{subdir}/{stored_filename}"

        self._client.put_object(
            Bucket=self.bucket, Key=self._key(storage_path), Body=data, ContentType=mime_type,
        )
        return stored_filename, storage_path, len(data), mime_type

    def delete(self, storage_path):
        # delete_object doesn't error on a missing key, matching
        # LocalStorageProvider.delete's silent-no-op-if-missing behavior.
        self._client.delete_object(Bucket=self.bucket, Key=self._key(storage_path))

    def full_path(self, storage_path):
        """Downloads the object to a fresh local temp file and returns its
        path - callers (pypdf, PIL, Flask's send_file) all need a real
        filesystem path, not an S3 key. The temp file is left in the OS temp
        dir rather than cleaned up immediately after use (callers read it
        exactly once, right after calling this); acceptable for this app's
        upload volume, and most PaaS hosts recycle the temp dir on
        redeploy/restart regardless."""
        from botocore.exceptions import ClientError

        try:
            response = self._client.get_object(Bucket=self.bucket, Key=self._key(storage_path))
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code in ("NoSuchKey", "404"):
                raise FileNotFoundError(f"No such object: {storage_path}") from e
            raise

        suffix = os.path.splitext(storage_path)[1]
        fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, "wb") as f:
            f.write(response["Body"].read())
        return tmp_path


def get_storage_provider(config):
    """Returns the configured StorageProvider. Mirrors
    app/ai/provider_factory.py's pattern: callers read config, never
    instantiate a provider class directly, so switching STORAGE_PROVIDER
    never requires touching a route."""
    if config.get("STORAGE_PROVIDER") == "s3":
        return S3StorageProvider(
            bucket=config["S3_BUCKET"],
            prefix=config.get("S3_PREFIX") or "",
            region_name=config.get("S3_REGION"),
            endpoint_url=config.get("S3_ENDPOINT_URL"),
            access_key_id=config.get("S3_ACCESS_KEY_ID"),
            secret_access_key=config.get("S3_SECRET_ACCESS_KEY"),
        )
    return LocalStorageProvider(config["UPLOAD_DIR"])
