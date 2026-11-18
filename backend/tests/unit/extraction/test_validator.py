import hashlib
import io
import zipfile

import pytest

from app.services.extraction import JD_KINDS, ExtractionError, validate_file
from app.services.extraction import validator as validator_module
from tests.unit.extraction.builders import make_docx, make_pdf

MB = 1024 * 1024


def zip_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("data_factory", "filename", "kind"),
    [
        (make_pdf, "resume.pdf", "pdf"),
        (make_docx, "resume.docx", "docx"),
        (make_pdf, "RESUME.PDF", "pdf"),  # extensions are case-insensitive
    ],
)
def test_valid_files_are_accepted(data_factory: object, filename: str, kind: str) -> None:
    data = data_factory()  # type: ignore[operator]

    result = validate_file(data, filename, max_bytes=5 * MB)

    assert result.kind == kind
    assert result.size_bytes == len(data)
    assert result.sha256 == hashlib.sha256(data).hexdigest()


def test_txt_is_accepted_only_where_allowed() -> None:
    data = b"Job Title: Data Scientist"

    assert validate_file(data, "jd.txt", max_bytes=MB, allowed=JD_KINDS).kind == "txt"
    with pytest.raises(ExtractionError) as exc:
        validate_file(data, "resume.txt", max_bytes=MB)  # resumes: PDF and DOCX only
    assert exc.value.code == "unsupported_type"
    assert "Accepted: .docx, .pdf" in exc.value.message


@pytest.mark.parametrize(
    ("data", "filename", "max_bytes", "code"),
    [
        (b"", "resume.pdf", MB, "empty_file"),
        (b"%PDF-" + b"0" * 2000, "resume.pdf", 1000, "file_too_large"),
        (b"MZ\x90\x00", "setup.exe", MB, "unsupported_type"),
        (b"just some text", "resume.pdf", MB, "unsupported_type"),  # .pdf name, not a PDF
        (b"%PDF-1.7 ...", "resume.docx", MB, "unsupported_type"),  # PDF content, .docx name
        (zip_bytes({"hello.txt": b"hi"}), "resume.docx", MB, "unsupported_type"),  # not Word
        (b"\x00\x01binary", "jd.txt", MB, "unsupported_type"),
    ],
    ids=[
        "empty",
        "too-large",
        "executable",
        "pdf-name-text-content",
        "docx-name-pdf-content",
        "zip-without-word-document",
        "binary-txt",
    ],
)
def test_invalid_files_are_rejected_with_a_reason(
    data: bytes, filename: str, max_bytes: int, code: str
) -> None:
    with pytest.raises(ExtractionError) as exc:
        validate_file(data, filename, max_bytes=max_bytes, allowed=JD_KINDS)

    assert exc.value.code == code
    assert exc.value.message  # always something to show the recruiter


def test_size_limit_message_names_the_limit() -> None:
    with pytest.raises(ExtractionError, match="larger than 5 MB"):
        validate_file(b"%PDF-" + b"0" * (5 * MB), "big.pdf", max_bytes=5 * MB)


def test_docx_that_unpacks_to_too_much_data_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(validator_module, "MAX_DOCX_UNCOMPRESSED_BYTES", 1000)
    bomb = zip_bytes(
        {
            "[Content_Types].xml": b"<Types/>",
            "word/document.xml": b"<w:document/>",
            "word/padding.bin": b"\x00" * 5000,  # compresses to almost nothing
        }
    )

    with pytest.raises(ExtractionError) as exc:
        validate_file(bomb, "resume.docx", max_bytes=MB)
    assert exc.value.code == "unsupported_type"
