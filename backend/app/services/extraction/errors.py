from typing import Literal

ExtractionErrorCode = Literal[
    "empty_file",
    "file_too_large",
    "unsupported_type",
    "corrupt_file",
    "encrypted_file",
    "scanned_pdf",
    "no_text",
]


class ExtractionError(Exception):
    """A file we can't turn into text. `message` is shown to the recruiter as-is."""

    def __init__(self, code: ExtractionErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
