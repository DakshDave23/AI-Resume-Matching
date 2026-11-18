"""Turn an uploaded PDF, DOCX or TXT file into clean plain text.

    validated = validate_file(data, filename, max_bytes=...)   # at upload time
    extracted = extract_text(data, validated.kind)              # in the pipeline

Both raise ExtractionError, whose `message` is safe to show to the recruiter.
"""

from dataclasses import dataclass

from app.services.extraction.cleaner import clean_text
from app.services.extraction.docx_reader import read_docx
from app.services.extraction.errors import ExtractionError, ExtractionErrorCode
from app.services.extraction.pdf_reader import read_pdf
from app.services.extraction.validator import (
    JD_KINDS,
    RESUME_KINDS,
    DocumentKind,
    ValidatedFile,
    validate_file,
)

# A text-based PDF page yields hundreds of characters; fewer means an image (design doc §5.1).
MIN_PDF_TEXT_CHARS = 100


@dataclass(frozen=True)
class ExtractedText:
    text: str
    kind: DocumentKind
    page_count: int | None  # PDFs only


def _decode_txt(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def extract_text(data: bytes, kind: DocumentKind) -> ExtractedText:
    page_count: int | None = None
    if kind == "pdf":
        raw, page_count = read_pdf(data)
    elif kind == "docx":
        raw = read_docx(data)
    else:
        raw = _decode_txt(data)

    text = clean_text(raw)
    if kind == "pdf" and page_count and len(text) < MIN_PDF_TEXT_CHARS:
        raise ExtractionError("scanned_pdf", "Looks like a scanned image; OCR is not enabled.")
    if not text:
        raise ExtractionError("no_text", "No readable text was found in the file.")
    return ExtractedText(text=text, kind=kind, page_count=page_count)


__all__ = [
    "JD_KINDS",
    "MIN_PDF_TEXT_CHARS",
    "RESUME_KINDS",
    "DocumentKind",
    "ExtractedText",
    "ExtractionError",
    "ExtractionErrorCode",
    "ValidatedFile",
    "extract_text",
    "validate_file",
]
