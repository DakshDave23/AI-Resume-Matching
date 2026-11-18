"""Job routes: create from pasted text or a file, list, read, and recruiter edits (§8)."""

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_embedder, get_model_loader
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.errors import AppError
from app.models import Job
from app.repositories.jobs import list_jobs
from app.schemas.jobs import (
    JobCreate,
    JobListOut,
    JobOut,
    JobRequirementOut,
    JobSkillOut,
    JobSummaryOut,
    RequirementsUpdate,
)
from app.services import jobs as job_service
from app.services.extraction import JD_KINDS, ExtractionError, extract_text, validate_file
from app.services.nlp.embedder import TextEncoder
from app.services.nlp.loader import ModelLoader

router = APIRouter(prefix="/jobs", tags=["jobs"])

# Extraction failure codes -> HTTP status (design doc §8).
EXTRACTION_STATUS = {
    "empty_file": 400,
    "file_too_large": 413,
    "unsupported_type": 415,
}  # anything else (corrupt, encrypted, scanned, no text) is 422


def job_out(job: Job) -> JobOut:
    parsed = job.parsed_json or {}
    skills = sorted(
        job.skills,
        key=lambda s: (s.requirement_type.value != "required", s.skill.canonical_name.lower()),
    )
    return JobOut(
        id=job.id,
        title=job.title,
        company=job.company,
        location=parsed.get("location"),
        seniority=parsed.get("seniority"),
        status=job.status,
        source_filename=job.source_filename,
        raw_text=job.raw_text,
        min_experience_years=_float(job.min_experience_years),
        max_experience_years=_float(job.max_experience_years),
        required_degree_level=job.required_degree_level,
        required_fields_of_study=job.required_fields_of_study,
        accepts_equivalent_experience=job.accepts_equivalent_experience,
        scoring_weights=job.scoring_weights,
        skills=[
            JobSkillOut(
                skill_id=s.skill_id,
                name=s.skill.canonical_name,
                category=s.skill.category,
                is_custom=s.skill.is_custom,
                requirement_type=s.requirement_type,
                weight=float(s.weight),
                min_years=_float(s.min_years),
                source_text=s.source_text,
                added_by=s.added_by,
            )
            for s in skills
        ],
        unmapped_skills=parsed.get("unmapped_skills", []),
        requirements=[
            JobRequirementOut(
                id=r.id,
                position=r.position,
                text=r.text,
                category=r.category,
                requirement_type=r.requirement_type,
            )
            for r in job.requirements
        ],
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=JobOut,
    summary="Create a job from pasted JD text",
    responses={503: {"description": "The embedding model is still loading"}},
)
def create_job(
    body: JobCreate,
    db: Session = Depends(get_db),
    encoder: TextEncoder = Depends(get_embedder),
) -> JobOut:
    return job_out(job_service.create_job(db, body.text, encoder, title=body.title))


@router.post(
    "/upload",
    status_code=status.HTTP_201_CREATED,
    response_model=JobOut,
    summary="Create a job from a JD file (PDF, DOCX or TXT)",
    responses={
        400: {"description": "Empty file"},
        413: {"description": "File larger than the upload limit"},
        415: {"description": "Not a PDF, DOCX or TXT file"},
        422: {"description": "Corrupt, encrypted or scanned file"},
        503: {"description": "The embedding model is still loading"},
    },
)
def upload_job(
    file: Annotated[UploadFile, File(description="One PDF, DOCX or TXT file")],
    db: Session = Depends(get_db),
    encoder: TextEncoder = Depends(get_embedder),
    settings: Settings = Depends(get_settings),
) -> JobOut:
    filename = file.filename or "job-description"
    data = file.file.read(settings.max_file_size_bytes + 1)  # never read more than the limit
    try:
        validated = validate_file(
            data, filename, max_bytes=settings.max_file_size_bytes, allowed=JD_KINDS
        )
        text = extract_text(data, validated.kind).text
    except ExtractionError as exc:
        raise AppError(EXTRACTION_STATUS.get(exc.code, 422), exc.message, code=exc.code) from exc
    if len(text.split()) < 3:
        raise AppError(422, "The file has too little text to be a job description", code="no_text")
    return job_out(job_service.create_job(db, text, encoder, source_filename=filename))


@router.get("", response_model=JobListOut, summary="List jobs, newest first")
def get_jobs(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
) -> JobListOut:
    summaries, total = list_jobs(db, limit=limit, offset=offset)
    return JobListOut(
        items=[
            JobSummaryOut(
                id=s.job.id,
                title=s.job.title,
                company=s.job.company,
                status=s.job.status,
                created_at=s.job.created_at,
                resume_count=s.resume_count,
                top_score=_float(s.top_score),
            )
            for s in summaries
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{job_id}",
    response_model=JobOut,
    summary="One job with its extracted requirements",
    responses={404: {"description": "No such job"}},
)
def get_job(job_id: uuid.UUID, db: Session = Depends(get_db)) -> JobOut:
    return job_out(job_service.get_job(db, job_id))


@router.patch(
    "/{job_id}/requirements",
    response_model=JobOut,
    summary="Save recruiter edits to skills, years, degree and fields",
    description=(
        "Only the fields sent change. `skills`, when sent, replaces the job's whole skill "
        "list: each chip names a skill by `skill_id`, or by `name` (canonical or alias); an "
        "unknown name adds a custom skill. Existing scores for the job are marked stale."
    ),
    responses={
        404: {"description": "No such job"},
        422: {"description": "Invalid edit (unknown skill id, duplicate skill, max < min)"},
        503: {"description": "A new custom skill needs the embedding model, still loading"},
    },
)
def update_requirements(
    job_id: uuid.UUID,
    body: RequirementsUpdate,
    db: Session = Depends(get_db),
    loader: ModelLoader = Depends(get_model_loader),
) -> JobOut:
    job = job_service.update_requirements(db, job_id, body, lambda: get_embedder(loader))
    return job_out(job)
