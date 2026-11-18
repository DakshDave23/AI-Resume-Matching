"""Accept a batch of resume files: validate, store, queue (design doc §2 step 3, §5.1, §8).

Each file is judged on its own. A bad one is rejected with a reason and never gets
a row; the rest form the batch. Only checks that are quick happen here (size,
type by magic bytes, duplicates); reading the text happens in the pipeline, so a
scanned PDF is accepted now and marked failed there.
"""

import uuid
from dataclasses import dataclass
from pathlib import PureWindowsPath

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import Resume, UploadBatch
from app.models.enums import FileType
from app.repositories.batches import StoredFile, create_batch
from app.repositories.resumes import clip
from app.services.extraction import RESUME_KINDS, ExtractionError, validate_file
from app.services.jobs import get_job
from app.services.storage import FileStore


@dataclass(frozen=True)
class Upload:
    filename: str  # as the browser sent it
    data: bytes


@dataclass(frozen=True)
class Rejection:
    filename: str
    code: str
    message: str


@dataclass(frozen=True)
class AcceptedBatch:
    batch: UploadBatch
    resumes: list[Resume]
    rejected: list[Rejection]


def display_name(filename: str) -> str:
    """The base name only: some browsers send "C:\\Users\\asha\\cv.pdf"."""
    name = PureWindowsPath(filename.replace("/", "\\")).name.strip()
    return clip(name, 255) or "resume"


def accept_batch(
    session: Session,
    store: FileStore,
    job_id: uuid.UUID,
    uploads: list[Upload],
    *,
    max_file_bytes: int,
    max_files: int,
) -> AcceptedBatch:
    """Store the valid files and create the batch with `queued` resumes. Commits."""
    get_job(session, job_id)  # 404 before touching the disk
    if not uploads:
        raise AppError(422, "Choose at least one file", code="no_files")
    if len(uploads) > max_files:
        raise AppError(422, f"Upload at most {max_files} files at once", code="too_many_files")

    accepted: list[StoredFile] = []
    rejected: list[Rejection] = []
    seen: set[str] = set()
    try:
        for upload in uploads:
            name = display_name(upload.filename)
            try:
                checked = validate_file(
                    upload.data, name, max_bytes=max_file_bytes, allowed=RESUME_KINDS
                )
            except ExtractionError as exc:
                rejected.append(Rejection(name, exc.code, exc.message))
                continue
            if checked.sha256 in seen:
                rejected.append(
                    Rejection(name, "duplicate_file", "The same file is already in this upload.")
                )
                continue
            seen.add(checked.sha256)
            stored = store.save(upload.data, checked.kind)
            accepted.append(
                StoredFile(name, stored, FileType(checked.kind), checked.size_bytes, checked.sha256)
            )

        if not accepted:
            raise AppError(
                422,
                "None of the files can be used",
                code="no_valid_files",
                details=[r.__dict__ for r in rejected],
            )
        batch, resumes = create_batch(session, job_id, accepted)
        session.commit()
    except BaseException:
        for file in accepted:  # no row will point at them
            store.delete(file.storage_path)
        raise
    return AcceptedBatch(batch, resumes, rejected)
