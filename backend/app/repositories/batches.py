"""Upload batches: create one with its queued resumes, count results, find unfinished work."""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import case, func, literal, select, update
from sqlalchemy.orm import Session

from app.models import Candidate, Resume, UploadBatch
from app.models.enums import BatchStatus, FileType, ParseStatus, batch_status_type


@dataclass(frozen=True)
class StoredFile:
    original_filename: str
    storage_path: str  # the FileStore name
    file_type: FileType
    size_bytes: int
    sha256: str


def create_batch(
    session: Session, job_id: uuid.UUID, files: list[StoredFile]
) -> tuple[UploadBatch, list[Resume]]:
    """A batch with one `queued` resume per accepted file, in upload order. Flushes only."""
    batch = UploadBatch(job_id=job_id, total_files=len(files))
    session.add(batch)
    session.flush()
    resumes = [
        Resume(
            batch_id=batch.id,
            original_filename=f.original_filename,
            storage_path=f.storage_path,
            file_type=f.file_type,
            file_size_bytes=f.size_bytes,
            file_sha256=f.sha256,
        )
        for f in files
    ]
    session.add_all(resumes)
    session.flush()
    return batch, resumes


def count_result(session: Session, batch_id: uuid.UUID, *, parsed: bool) -> None:
    """Count one finished resume; the last one completes the batch, in the same statement.

    One UPDATE reads and writes the counters together, so two workers finishing at
    once can't lose a count, and the status can never disagree with the counts.
    (In SET, column names mean the values before this update.)
    """
    batch = UploadBatch
    processed = batch.processed_files + (1 if parsed else 0)
    failed = batch.failed_files + (0 if parsed else 1)
    finished = processed + failed == batch.total_files
    status = case(
        (finished & (failed == 0), literal(BatchStatus.COMPLETED, batch_status_type)),
        (finished, literal(BatchStatus.COMPLETED_WITH_ERRORS, batch_status_type)),
        else_=batch.status,
    )
    session.execute(
        update(batch)
        .where(batch.id == batch_id)
        .values(
            processed_files=processed,
            failed_files=failed,
            status=status,
            completed_at=case((finished, func.now()), else_=batch.completed_at),
        )
    )


def pending_resume_ids(session: Session, batch_id: uuid.UUID) -> list[uuid.UUID]:
    """Resumes of the batch not yet parsed or failed (after a restart: queued or mid-parse)."""
    return list(
        session.scalars(
            select(Resume.id)
            .where(
                Resume.batch_id == batch_id,
                Resume.parse_status.in_([ParseStatus.QUEUED, ParseStatus.PARSING]),
            )
            .order_by(Resume.created_at, Resume.original_filename)
        )
    )


def unfinished_batch_ids(session: Session) -> list[uuid.UUID]:
    return list(
        session.scalars(
            select(UploadBatch.id)
            .where(UploadBatch.status == BatchStatus.PROCESSING)
            .order_by(UploadBatch.created_at)
        )
    )


@dataclass(frozen=True)
class FileProgress:
    resume_id: uuid.UUID
    original_filename: str
    file_type: FileType
    file_size_bytes: int
    parse_status: ParseStatus
    parse_error: str | None
    parse_confidence: Decimal | None
    candidate_name: str | None


def batch_progress(
    session: Session, batch_id: uuid.UUID
) -> tuple[UploadBatch, list[FileProgress]] | None:
    """A batch and each file's state, for polling every 2 s: two small queries.

    Only the columns the status view shows are read; never raw text or vectors.
    """
    batch = session.get(UploadBatch, batch_id, populate_existing=True)
    if batch is None:
        return None
    rows = session.execute(
        select(
            Resume.id,
            Resume.original_filename,
            Resume.file_type,
            Resume.file_size_bytes,
            Resume.parse_status,
            Resume.parse_error,
            Resume.parse_confidence,
            Candidate.full_name,
        )
        .outerjoin(Candidate, Candidate.id == Resume.candidate_id)
        .where(Resume.batch_id == batch_id)
        .order_by(Resume.created_at, Resume.original_filename)
    ).all()
    return batch, [FileProgress(*row) for row in rows]
