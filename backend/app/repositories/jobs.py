"""Save a parsed JD: requirements with vectors, skills, years, degree.

The job routes (step 19) create a `Job` row with its title and raw text, then call
`save_parsed_job`. Saving again replaces the parsed requirements and skills.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session, selectinload

from app.models import Job, JobRequirement, JobSkill, MatchResult, Resume, UploadBatch
from app.models.enums import JobStatus, SkillAddedBy
from app.repositories.resumes import clip
from app.repositories.skills import skill_ids
from app.services.nlp.vectors import JobVectors
from app.services.parsing.jd_parser import JobParse


def _years(value: float | None) -> Decimal | None:
    return Decimal(str(round(value, 1))) if value is not None else None


def parsed_json(parsed: JobParse) -> dict[str, Any]:
    """What the job tables don't hold, for the review screen and for debugging."""
    return {
        "title": parsed.title,
        "location": parsed.location,
        "seniority": parsed.seniority.value,
        "preferred_degree_level": parsed.preferred_degree_level,
        "unmapped_skills": list(parsed.unmapped),
        "sections": parsed.segmentation.names(),
    }


def save_parsed_job(session: Session, job: Job, parsed: JobParse, vectors: JobVectors) -> None:
    """Store what the JD parser found on `job` and mark it parsed. Flushes, doesn't commit.

    The title is the caller's choice (the recruiter's, or the parsed one); the company
    is filled from the JD only when the job doesn't have one.
    """
    if len(vectors.requirements) != len(parsed.requirements):
        raise ValueError("vectors don't line up with the requirements they were made from")
    for model in (JobRequirement, JobSkill):
        session.execute(delete(model).where(model.job_id == job.id))

    job.company = job.company or clip(parsed.company, 200)
    job.min_experience_years = _years(parsed.min_experience_years)
    job.max_experience_years = _years(parsed.max_experience_years)
    job.required_degree_level = parsed.degree_level
    job.required_fields_of_study = list(parsed.fields_of_study)
    job.accepts_equivalent_experience = parsed.accepts_equivalent_experience
    job.parsed_json = parsed_json(parsed)
    job.embedding = vectors.document.tolist() if vectors.document is not None else None
    job.status = JobStatus.PARSED

    for position, (requirement, vector) in enumerate(
        zip(parsed.requirements, vectors.requirements, strict=True)
    ):
        session.add(
            JobRequirement(
                job_id=job.id,
                text=requirement.text,
                category=requirement.category,
                requirement_type=requirement.requirement_type,
                position=position,
                embedding=vector.tolist(),
            )
        )

    ids = skill_ids(session, (s.name for s in parsed.skills))
    for skill in parsed.skills:
        session.add(
            JobSkill(
                job_id=job.id,
                skill_id=ids[skill.name],
                requirement_type=skill.requirement_type,
                weight=Decimal(str(skill.default_weight)),
                min_years=_years(skill.min_years),
                source_text=skill.source_text,
                added_by=SkillAddedBy.PARSER,
            )
        )
    session.flush()


def load_job(session: Session, job_id: uuid.UUID) -> Job | None:
    """A job with its requirements and skills (and each skill's name), in three queries."""
    return session.scalars(
        select(Job)
        .where(Job.id == job_id)
        .options(
            selectinload(Job.requirements),
            selectinload(Job.skills).selectinload(JobSkill.skill),
        )
        .execution_options(populate_existing=True)
    ).one_or_none()


@dataclass(frozen=True)
class JobSummary:
    job: Job
    resume_count: int
    top_score: Decimal | None


def list_jobs(session: Session, *, limit: int, offset: int) -> tuple[list[JobSummary], int]:
    """Newest first, each with its resume count and best score, in one query (plus a count)."""
    resumes = (
        select(UploadBatch.job_id, func.count(Resume.id).label("resume_count"))
        .join(Resume, Resume.batch_id == UploadBatch.id)
        .group_by(UploadBatch.job_id)
        .subquery()
    )
    scores = (
        select(MatchResult.job_id, func.max(MatchResult.overall_score).label("top_score"))
        .group_by(MatchResult.job_id)
        .subquery()
    )
    rows = session.execute(
        select(Job, func.coalesce(resumes.c.resume_count, 0), scores.c.top_score)
        .outerjoin(resumes, resumes.c.job_id == Job.id)
        .outerjoin(scores, scores.c.job_id == Job.id)
        .order_by(Job.created_at.desc(), Job.id)
        .limit(limit)
        .offset(offset)
    ).all()
    total = session.scalar(select(func.count()).select_from(Job)) or 0
    return [JobSummary(job, count, top) for job, count, top in rows], total


def mark_matches_stale(session: Session, job_id: uuid.UUID) -> int:
    """After a requirement edit, existing scores no longer describe the job."""
    result = session.execute(
        update(MatchResult)
        .where(MatchResult.job_id == job_id, MatchResult.is_stale.is_(False))
        .values(is_stale=True)
    )
    return int(getattr(result, "rowcount", 0) or 0)
