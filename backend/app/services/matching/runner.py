"""Score resumes against their job and keep the job's ranking up to date."""

import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Resume, UploadBatch
from app.models.enums import ParseStatus
from app.repositories.matches import assign_ranks, upsert_match
from app.services.matching.inputs import load_candidate
from app.services.matching.scorer import MatchOutcome, ScoringJob, load_scoring_job, score_candidate
from app.services.nlp.embedder import TextEncoder


def score_resume(
    session: Session, job: ScoringJob, resume_id: uuid.UUID, *, today: date, encoder: TextEncoder
) -> MatchOutcome:
    """Score one parsed resume and store the result (unranked). Flushes, doesn't commit."""
    outcome = score_candidate(job, load_candidate(session, resume_id), today=today, encoder=encoder)
    upsert_match(session, job.job_id, resume_id, outcome)
    return outcome


def parsed_resume_ids(session: Session, job_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        session.scalars(
            select(Resume.id)
            .join(UploadBatch, UploadBatch.id == Resume.batch_id)
            .where(UploadBatch.job_id == job_id, Resume.parse_status == ParseStatus.PARSED)
            .order_by(Resume.created_at, Resume.original_filename)
        )
    )


def score_job(
    session: Session,
    job_id: uuid.UUID,
    encoder: TextEncoder,
    *,
    today: date,
    resume_ids: Sequence[uuid.UUID] | None = None,
) -> int:
    """(Re)score parsed resumes of a job (default: all of them), then re-rank. Commits."""
    job = load_scoring_job(session, job_id, encoder)
    ids = parsed_resume_ids(session, job_id) if resume_ids is None else list(resume_ids)
    for resume_id in ids:
        score_resume(session, job, resume_id, today=today, encoder=encoder)
    assign_ranks(session, job_id)
    session.commit()
    return len(ids)
