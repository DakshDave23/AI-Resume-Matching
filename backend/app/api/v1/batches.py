"""Resume upload and batch progress (design doc §2 and §8)."""

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_embedder, get_file_store, get_session_factory
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.errors import AppError
from app.repositories.batches import batch_progress
from app.schemas.batches import (
    AcceptedFileOut,
    BatchCreatedOut,
    BatchFileOut,
    BatchStatusOut,
    RejectedFileOut,
)
from app.services.nlp.embedder import TextEncoder
from app.services.parsing.resume_parser import MIN_CONFIDENCE
from app.services.pipeline import Pipeline, SessionFactory
from app.services.storage import FileStore
from app.services.uploads import Upload, accept_batch

router = APIRouter(tags=["resumes"])


@router.post(
    "/jobs/{job_id}/resumes",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchCreatedOut,
    summary="Upload 1-50 resumes (PDF or DOCX) for a job",
    description=(
        "Returns at once with the batch id. Each valid file is stored and parsed in the "
        "background; poll the batch for progress. Invalid files are listed under `rejected` "
        "with a reason and are not part of the batch."
    ),
    responses={
        404: {"description": "No such job"},
        422: {"description": "No files, more than the limit, or none of them usable"},
        503: {"description": "The embedding model is still loading"},
    },
)
def upload_resumes(
    job_id: uuid.UUID,
    files: Annotated[list[UploadFile], File(description="1-50 PDF or DOCX files")],
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    store: FileStore = Depends(get_file_store),
    encoder: TextEncoder = Depends(get_embedder),
    sessions: SessionFactory = Depends(get_session_factory),
    settings: Settings = Depends(get_settings),
) -> BatchCreatedOut:
    limit = settings.max_file_size_bytes
    uploads = [
        # Read one byte past the limit: enough to know a file is too big, never more.
        Upload(f.filename or "resume", f.file.read(limit + 1))
        for f in files[: settings.max_batch_files + 1]
    ]
    return start_batch(
        job_id, uploads, background, db=db, store=store, encoder=encoder,
        sessions=sessions, settings=settings,
    )  # fmt: skip


def start_batch(
    job_id: uuid.UUID,
    uploads: list[Upload],
    background: BackgroundTasks,
    *,
    db: Session,
    store: FileStore,
    encoder: TextEncoder,
    sessions: SessionFactory,
    settings: Settings,
) -> BatchCreatedOut:
    """Check and store the files, then parse them in the background (also used for samples)."""
    result = accept_batch(
        db,
        store,
        job_id,
        uploads,
        max_file_bytes=settings.max_file_size_bytes,
        max_files=settings.max_batch_files,
    )
    pipeline = Pipeline(sessions, store, encoder, region=settings.phone_default_region)
    background.add_task(pipeline.run_batch, result.batch.id, [r.id for r in result.resumes])

    return BatchCreatedOut(
        batch_id=result.batch.id,
        job_id=job_id,
        status=result.batch.status,
        total_files=result.batch.total_files,
        accepted=[
            AcceptedFileOut(
                resume_id=r.id,
                filename=r.original_filename,
                size_bytes=r.file_size_bytes,
                parse_status=r.parse_status,
            )
            for r in result.resumes
        ],
        rejected=[RejectedFileOut(**r.__dict__) for r in result.rejected],
    )


@router.get(
    "/batches/{batch_id}",
    response_model=BatchStatusOut,
    summary="Progress of an upload batch, with each file's parse status",
    description=(
        "Poll this every couple of seconds until `status` is no longer `processing`. "
        "Failed files carry a reason in `parse_error`."
    ),
    responses={404: {"description": "No such batch"}},
)
def get_batch(
    batch_id: uuid.UUID, response: Response, db: Session = Depends(get_db)
) -> BatchStatusOut:
    found = batch_progress(db, batch_id)
    if found is None:
        raise AppError(404, "Batch not found")
    batch, files = found
    response.headers["Cache-Control"] = "no-store"  # it changes every second while parsing
    return BatchStatusOut(
        batch_id=batch.id,
        job_id=batch.job_id,
        status=batch.status,
        total_files=batch.total_files,
        processed_files=batch.processed_files,
        failed_files=batch.failed_files,
        pending_files=batch.total_files - batch.processed_files - batch.failed_files,
        created_at=batch.created_at,
        completed_at=batch.completed_at,
        files=[
            BatchFileOut(
                resume_id=f.resume_id,
                filename=f.original_filename,
                file_type=f.file_type,
                size_bytes=f.file_size_bytes,
                parse_status=f.parse_status,
                parse_error=f.parse_error,
                parse_confidence=float(f.parse_confidence)
                if f.parse_confidence is not None
                else None,
                needs_review=(
                    f.parse_confidence is not None
                    and f.parse_confidence < Decimal(str(MIN_CONFIDENCE))
                ),
                candidate_name=f.candidate_name,
            )
            for f in files
        ],
    )
