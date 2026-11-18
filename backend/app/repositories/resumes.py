"""Save a parsed resume: candidate, roles, education, skills, chunks and vectors.

The upload pipeline (step 20) calls `save_parsed_resume` once a file has been
extracted, parsed, chunked and embedded. Saving again replaces everything that
was parsed before, so a re-parse never leaves stale rows behind.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Candidate, Education, Resume, ResumeChunk, ResumeSkill, WorkExperience
from app.models.enums import ParseStatus
from app.repositories.skills import skill_ids
from app.services.nlp.vectors import ResumeVectors
from app.services.parsing.chunker import Chunk
from app.services.parsing.contact import ContactInfo
from app.services.parsing.dates import YearMonth
from app.services.parsing.resume_parser import ParsedResume

MAX_SMALLINT = 32767


def clip(text: str | None, length: int) -> str | None:
    """Fit a VARCHAR(length) column; parsed text is never trusted to be short."""
    if text is None:
        return None
    return text if len(text) <= length else text[: length - 1] + "…"


def _first_of_month(value: YearMonth | None) -> date | None:
    return value.as_date() if value is not None else None


def _month(value: YearMonth | None) -> str | None:
    return f"{value.year}-{value.month:02d}" if value is not None else None


def upsert_candidate(session: Session, contact: ContactInfo) -> uuid.UUID | None:
    """The candidate for this contact block: matched by email, else a new one.

    One INSERT ... ON CONFLICT on the lower(email) index, so two resumes of the same
    person parsed at once can't create two candidates. Values from the newer resume
    win; a field it doesn't have keeps the old value. No name, email or phone: no candidate.
    """
    if not (contact.name or contact.email or contact.phone):
        return None
    values = {
        "full_name": clip(contact.name, 200),
        "email": clip(contact.email, 254),
        "phone": contact.phone,
        "location": clip(contact.location, 200),
        "linkedin_url": contact.linkedin_url,
        "github_url": contact.github_url,
    }
    statement = insert(Candidate).values(values)
    if contact.email is not None:
        new = statement.excluded
        statement = statement.on_conflict_do_update(
            index_elements=[func.lower(Candidate.email)],
            index_where=Candidate.email.is_not(None),
            set_={
                column: func.coalesce(getattr(new, column), getattr(Candidate, column))
                for column in values
                if column != "email"
            },
        )
    candidate_id: uuid.UUID = session.execute(statement.returning(Candidate.id)).scalar_one()
    return candidate_id


def parsed_json(parsed: ParsedResume, today: date) -> dict[str, Any]:
    """What the tables don't hold, kept for the UI and for debugging."""
    work = parsed.work
    return {
        "checks": parsed.checks,
        "experience_source": work.source,
        "roles": [
            {
                "title": role.title,
                "company": role.company,
                "location": role.location,
                "start": _month(role.dates.start) if role.dates else None,
                "end": _month(role.dates.end) if role.dates else None,
                "date_precision": role.dates.precision if role.dates else None,
                "is_current": role.is_current,
                "is_internship": role.is_internship,
                "months": role.months(today),
            }
            for role in work.roles
        ],
        "skill_months": parsed.skill_months,
        "unmapped_skills": list(parsed.skills.unmapped),
    }


def _clear_parse(session: Session, resume_id: uuid.UUID) -> None:
    for model in (ResumeSkill, WorkExperience, Education, ResumeChunk):
        session.execute(delete(model).where(model.resume_id == resume_id))


def save_parsed_resume(
    session: Session,
    resume: Resume,
    *,
    text: str,
    parsed: ParsedResume,
    chunks: list[Chunk],
    vectors: ResumeVectors,
    today: date,
) -> None:
    """Store everything parsed from `resume`'s file and mark it parsed. Flushes, doesn't commit."""
    if len(vectors.chunks) != len(chunks) or len(vectors.roles) != len(parsed.work.roles):
        raise ValueError("vectors don't line up with the chunks and roles they were made from")
    _clear_parse(session, resume.id)

    work, education = parsed.work, parsed.education
    resume.candidate_id = upsert_candidate(session, parsed.contact)
    resume.raw_text = text
    resume.sections = parsed.sections.as_dict()
    resume.parsed_json = parsed_json(parsed, today)
    resume.total_experience_months = work.total_months
    resume.highest_degree_level = education.highest_level
    resume.current_title = clip(work.current_title, 200)
    resume.parse_confidence = Decimal(str(round(parsed.confidence, 2)))
    resume.embedding = vectors.document.tolist() if vectors.document is not None else None
    resume.parse_status = ParseStatus.PARSED
    resume.parse_error = None
    resume.parsed_at = datetime.now(UTC)

    for role, vector in zip(work.roles, vectors.roles, strict=True):
        dates = role.dates
        session.add(
            WorkExperience(
                resume_id=resume.id,
                job_title=clip(role.title, 200),
                company=clip(role.company, 200),
                start_date=_first_of_month(dates.start) if dates else None,
                end_date=_first_of_month(dates.end) if dates else None,  # None while current
                is_current=role.is_current,
                duration_months=role.months(today),
                description=role.description or None,
                embedding=vector.tolist() if vector is not None else None,
            )
        )

    for entry in education.entries:
        session.add(
            Education(
                resume_id=resume.id,
                degree_raw=clip(entry.degree, 200),
                degree_level=entry.level,
                field_of_study=clip(entry.field, 200),
                institution=clip(entry.institution, 200),
                graduation_year=entry.year,
            )
        )

    ids = skill_ids(session, (s.name for s in parsed.skills.skills))
    for skill in parsed.skills.skills:
        months = parsed.skill_months.get(skill.name)
        session.add(
            ResumeSkill(
                resume_id=resume.id,
                skill_id=ids[skill.name],
                sources=list(skill.sources),
                mention_count=min(skill.mention_count, MAX_SMALLINT),
                # The table stores years; the parser counts months.
                years_used=Decimal(str(round(months / 12, 1))) if months else None,
                evidence=skill.evidence,
            )
        )

    for index, (chunk, vector) in enumerate(zip(chunks, vectors.chunks, strict=True)):
        session.add(
            ResumeChunk(
                resume_id=resume.id,
                section=chunk.section,
                chunk_index=index,
                text=chunk.text,
                embedding=vector.tolist(),
            )
        )
    session.flush()


def mark_failed(resume: Resume, reason: str) -> None:
    """A file that can't be parsed keeps its row, with a reason the recruiter can read."""
    resume.parse_status = ParseStatus.FAILED
    resume.parse_error = reason
