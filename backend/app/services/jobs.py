"""Create jobs from JD text and apply recruiter edits (design doc §5.4 and §8).

The routes stay thin: they validate input and map errors to HTTP; the work is here.
"""

import uuid
from collections.abc import Callable
from decimal import Decimal
from pathlib import PurePath

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import Job, JobSkill, Skill
from app.models.enums import RequirementType, SkillAddedBy, SkillCategory
from app.repositories.jobs import load_job, mark_matches_stale, save_parsed_job
from app.repositories.resumes import clip
from app.repositories.skills import add_custom_skill, find_skill
from app.schemas.jobs import RequirementsUpdate, SkillRequirementIn
from app.services.nlp.embedder import TextEncoder
from app.services.nlp.vectors import embed_job
from app.services.parsing.jd_parser import parse_job

UNTITLED = "Untitled job"
DEFAULT_CUSTOM_CATEGORY = SkillCategory.TOOL
WEIGHTS = {RequirementType.REQUIRED: Decimal("1.00"), RequirementType.PREFERRED: Decimal("0.50")}


def create_job(
    session: Session,
    text: str,
    encoder: TextEncoder,
    *,
    title: str | None = None,
    source_filename: str | None = None,
) -> Job:
    """Parse, embed and save a JD. The title is the recruiter's, else the JD's, else the file's."""
    parsed = parse_job(text)
    stem = PurePath(source_filename).stem if source_filename else None
    job = Job(
        title=clip(title or parsed.title or stem or UNTITLED, 200),
        raw_text=text,
        source_filename=clip(source_filename, 255),
    )
    session.add(job)
    session.flush()
    save_parsed_job(session, job, parsed, embed_job(parsed.requirements, encoder))
    session.commit()
    return get_job(session, job.id)


def get_job(session: Session, job_id: uuid.UUID) -> Job:
    job = load_job(session, job_id)
    if job is None:
        raise AppError(404, "Job not found")
    return job


def _years(value: float | None) -> Decimal | None:
    return Decimal(str(round(value, 1))) if value is not None else None


def _resolve(
    session: Session, chip: SkillRequirementIn, encoder: Callable[[], TextEncoder]
) -> Skill:
    if chip.skill_id is not None:
        skill = session.get(Skill, chip.skill_id)
        if skill is None:
            raise AppError(422, f"No skill with id {chip.skill_id}", code="unknown_skill")
        return skill
    assert chip.name is not None  # the schema guarantees one of the two
    found = find_skill(session, chip.name)
    if found is not None:
        return found
    category = chip.category or DEFAULT_CUSTOM_CATEGORY
    return add_custom_skill(session, chip.name, category, encoder())


def _replace_skills(
    session: Session, job: Job, chips: list[SkillRequirementIn], encoder: Callable[[], TextEncoder]
) -> None:
    """The recruiter sends the whole chip list; unchanged chips keep `added_by = parser`."""
    before = {s.skill_id: s for s in job.skills}
    wanted: dict[int, tuple[SkillRequirementIn, Skill]] = {}
    for chip in chips:
        skill = _resolve(session, chip, encoder)
        if skill.id in wanted:
            raise AppError(422, f"{skill.canonical_name} is listed twice", code="duplicate_skill")
        wanted[skill.id] = (chip, skill)

    for skill_id, old in before.items():
        if skill_id not in wanted:
            session.delete(old)
    for skill_id, (chip, _skill) in wanted.items():
        min_years = _years(chip.min_years)
        existing = before.get(skill_id)
        if existing is not None and (existing.requirement_type, existing.min_years) == (
            chip.requirement_type,
            min_years,
        ):
            continue  # an untouched chip keeps added_by and its source text
        row = existing or JobSkill(job_id=job.id, skill_id=skill_id, source_text=None)
        if existing is None:
            session.add(row)
        row.requirement_type = chip.requirement_type
        row.weight = WEIGHTS[chip.requirement_type]
        row.min_years = min_years
        row.added_by = SkillAddedBy.RECRUITER


def update_requirements(
    session: Session,
    job_id: uuid.UUID,
    changes: RequirementsUpdate,
    encoder: Callable[[], TextEncoder],
) -> Job:
    """Apply recruiter edits; existing scores for the job are marked stale.

    `encoder` is called only if a chip adds a custom skill, so most edits work even
    while the embedding model is still loading.
    """
    job = get_job(session, job_id)
    sent = changes.model_fields_set

    # Check the years against what is saved before changing anything.
    low = (
        _years(changes.min_experience_years)
        if "min_experience_years" in sent
        else job.min_experience_years
    )
    high = (
        _years(changes.max_experience_years)
        if "max_experience_years" in sent
        else job.max_experience_years
    )
    if low is not None and high is not None and high < low:
        raise AppError(
            422,
            f"Maximum experience ({high} years) is below the minimum ({low} years)",
            code="invalid_experience_range",
        )

    if "skills" in sent and changes.skills is not None:
        _replace_skills(session, job, changes.skills, encoder)
    job.min_experience_years, job.max_experience_years = low, high
    if "required_degree_level" in sent:
        level = changes.required_degree_level
        job.required_degree_level = int(level) if level is not None else None
    if "required_fields_of_study" in sent:
        job.required_fields_of_study = list(dict.fromkeys(changes.required_fields_of_study or []))
    if (
        "accepts_equivalent_experience" in sent
        and changes.accepts_equivalent_experience is not None
    ):
        job.accepts_equivalent_experience = changes.accepts_equivalent_experience
    job.updated_at = func.now()  # skill-only edits don't touch the job row otherwise
    mark_matches_stale(session, job.id)
    session.commit()
    return get_job(session, job.id)
