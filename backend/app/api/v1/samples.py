"""The jobs page's "Load sample data" button (design doc §9): the demo in one click."""

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_embedder, get_file_store, get_session_factory
from app.api.v1.batches import start_batch
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.errors import AppError
from app.schemas.batches import BatchCreatedOut
from app.services import jobs as job_service
from app.services.nlp.embedder import TextEncoder
from app.services.pipeline import SessionFactory
from app.services.storage import FileStore
from app.services.uploads import Upload

router = APIRouter(tags=["samples"])

RESUME_SUFFIXES = {".pdf", ".docx"}


def _sample_files(settings: Settings) -> tuple[Path, list[Path]]:
    root = settings.sample_data_dir
    jd = root / settings.sample_jd
    resumes = sorted(
        p for p in (root / "resumes").glob("*") if p.is_file() and p.suffix in RESUME_SUFFIXES
    )
    if not jd.is_file() or not resumes:
        raise AppError(404, "Sample data isn't available on this server", code="no_sample_data")
    return jd, resumes[: settings.max_batch_files]


@router.post(
    "/sample-data",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchCreatedOut,
    summary="Create the sample Backend Java job and upload the 15 sample resumes",
    description=(
        "Synthetic data only. Returns the new job and batch at once; the resumes are parsed "
        "and scored in the background, exactly as an upload is. One of them is a scanned PDF "
        "that fails with its reason."
    ),
    responses={
        404: {"description": "The server has no sample data"},
        503: {"description": "The embedding model is still loading"},
    },
)
def load_sample_data(
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    store: FileStore = Depends(get_file_store),
    encoder: TextEncoder = Depends(get_embedder),
    sessions: SessionFactory = Depends(get_session_factory),
    settings: Settings = Depends(get_settings),
) -> BatchCreatedOut:
    jd, resumes = _sample_files(settings)
    job = job_service.create_job(
        db, jd.read_text(encoding="utf-8"), encoder, source_filename=jd.name
    )
    uploads = [Upload(p.name, p.read_bytes()) for p in resumes]
    return start_batch(
        job.id, uploads, background, db=db, store=store, encoder=encoder,
        sessions=sessions, settings=settings,
    )  # fmt: skip
