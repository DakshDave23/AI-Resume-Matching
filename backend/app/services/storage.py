"""Uploaded files on local disk, under UUID names (design doc §2 and §8).

The recruiter's file name is kept in the database for display only; on disk every
file is `<uuid>.<ext>`, so a name like "../../etc/passwd" can never become a path.
"""

import re
import uuid
from pathlib import Path

from app.core.config import BACKEND_DIR, Settings
from app.services.extraction import DocumentKind

_STORED_NAME = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.(pdf|docx)$"
)


class FileStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    @classmethod
    def from_settings(cls, settings: Settings) -> "FileStore":
        """UPLOAD_DIR, resolved against backend/ when relative (not wherever uvicorn started)."""
        root = settings.upload_dir
        return cls(root if root.is_absolute() else (BACKEND_DIR / root).resolve())

    def save(self, data: bytes, kind: DocumentKind) -> str:
        """Write the file and return its stored name. Written whole or not at all."""
        self.root.mkdir(parents=True, exist_ok=True)
        name = f"{uuid.uuid4()}.{kind}"
        partial = self.root / f".{name}.part"
        partial.write_bytes(data)
        partial.replace(self.root / name)  # atomic: a reader never sees half a file
        return name

    def path(self, name: str) -> Path:
        if not _STORED_NAME.fullmatch(name):
            raise ValueError(f"not a stored file name: {name!r}")
        return self.root / name

    def read(self, name: str) -> bytes:
        return self.path(name).read_bytes()

    def delete(self, name: str) -> None:
        self.path(name).unlink(missing_ok=True)
