"""Save a parsed JD: requirements with vectors, skills, years, degree.

The job routes (step 19) create a `Job` row with its title and raw text, then call
`save_parsed_job`. Saving again replaces the parsed requirements and skills.
"""

from decimal import Decimal
from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import Job, JobRequirement, JobSkill
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
