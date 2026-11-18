"""Check an upload before parsing it (design doc §5.1, step 1).

The file's *content* decides its type, never just the extension: a PDF starts
with "%PDF-", a DOCX is a ZIP archive containing word/document.xml. A file
whose content and extension disagree is rejected.
"""

import hashlib
import io
import zipfile
from dataclasses import dataclass
from pathlib import PurePath
from typing import Literal

from app.services.extraction.errors import ExtractionError

DocumentKind = Literal["pdf", "docx", "txt"]

RESUME_KINDS: frozenset[DocumentKind] = frozenset({"pdf", "docx"})
JD_KINDS: frozenset[DocumentKind] = frozenset({"pdf", "docx", "txt"})

# A DOCX that unpacks to more than this is treated as a zip bomb, not a resume.
MAX_DOCX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_DOCX_MEMBERS = 1000


@dataclass(frozen=True)
class ValidatedFile:
    kind: DocumentKind
    size_bytes: int
    sha256: str


def _extension(filename: str) -> str:
    return PurePath(filename).suffix.lower().lstrip(".")


def _looks_like_pdf(data: bytes) -> bool:
    # The spec allows a little junk before the header; real files almost always start with it.
    return b"%PDF-" in data[:1024]


def _check_docx(data: bytes) -> None:
    if not zipfile.is_zipfile(io.BytesIO(data)):
        raise ExtractionError("unsupported_type", "The file is not a valid Word (.docx) document.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = archive.infolist()
    except zipfile.BadZipFile as exc:
        raise ExtractionError("corrupt_file", "The Word document is damaged.") from exc

    names = {m.filename for m in members}
    if "word/document.xml" not in names or "[Content_Types].xml" not in names:
        raise ExtractionError(
            "unsupported_type",
            "The file is a ZIP archive but not a Word (.docx) document.",
        )
    if len(members) > MAX_DOCX_MEMBERS or (
        sum(m.file_size for m in members) > MAX_DOCX_UNCOMPRESSED_BYTES
    ):
        raise ExtractionError("unsupported_type", "The Word document is unusually large inside.")


def _check_txt(data: bytes) -> None:
    if b"\x00" in data[:8192]:
        raise ExtractionError("unsupported_type", "The file is not a plain-text document.")


def validate_file(
    data: bytes,
    filename: str,
    *,
    max_bytes: int,
    allowed: frozenset[DocumentKind] = RESUME_KINDS,
) -> ValidatedFile:
    """Return the file's kind, size and SHA-256, or raise ExtractionError with a reason."""
    if not data:
        raise ExtractionError("empty_file", "The file is empty.")
    if len(data) > max_bytes:
        limit_mb = max_bytes / (1024 * 1024)
        raise ExtractionError("file_too_large", f"The file is larger than {limit_mb:g} MB.")

    extension = _extension(filename)
    if extension not in allowed:
        accepted = ", ".join(f".{k}" for k in sorted(allowed))
        raise ExtractionError("unsupported_type", f"Unsupported file type. Accepted: {accepted}.")
    kind: DocumentKind = extension  # narrowed to a DocumentKind by the check above

    if kind == "pdf":
        if not _looks_like_pdf(data):
            raise ExtractionError("unsupported_type", "The file has a .pdf name but is not a PDF.")
    elif kind == "docx":
        _check_docx(data)
    else:
        _check_txt(data)

    return ValidatedFile(kind=kind, size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
