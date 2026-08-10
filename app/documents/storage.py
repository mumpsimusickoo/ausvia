"""
StorageProvider abstraction (spec section 42). LocalStorageProvider is the only
implementation for now; a future cloud object-storage provider (S3-compatible)
can implement the same interface without touching callers.
"""
import os
import uuid
from abc import ABC, abstractmethod

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
            f"Unsupported file type '.{ext}'. Allowed: {', '.join(sorted(ALLOWED_TYPES))}."
        )

    header = file_storage.stream.read(16)
    file_storage.stream.seek(0)
    mime_type, signatures = ALLOWED_TYPES[ext]
    if not any(header.startswith(sig) for sig in signatures):
        raise UnsupportedFileError(
            "File content doesn't match its extension. The file may be corrupted or mislabeled."
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
            raise UnsupportedFileError("File exceeds the 15 MB size limit.")

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
