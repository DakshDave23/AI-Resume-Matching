"""Load what the scorers need, from the database or straight from the parsers."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Education,
    Job,
    JobRequirement,
    JobSkill,
    Resume,
    ResumeChunk,
    ResumeSkill,
    Skill,
    WorkExperience,
)
from app.repositories.skills import skill_embedding_text
from app.services.matching.education import DegreeInput
from app.services.matching.experience import RoleInput
from app.services.matching.semantic import RequirementInput
from app.services.matching.skills import CandidateSkillInput, JobSkillInput, Passage
from app.services.nlp.embedder import TextEncoder
from app.services.nlp.taxonomy import get_taxonomy
from app.services.nlp.vectors import ResumeVectors, Vector
from app.services.parsing.chunker import Chunk
from app.services.parsing.experience import is_internship_title
from app.services.parsing.jd_parser import JobParse
from app.services.parsing.resume_parser import ParsedResume


@dataclass(frozen=True)
class CandidateData:
    skills: list[CandidateSkillInput]
    passages: list[Passage]  # every chunk, in resume order
    text: str
    vector: Vector | None  # the whole-resume vector
    roles: list[RoleInput]
    total_months: int | None
    stated_months: int | None  # the total a resume without dates states in its summary
    degrees: list[DegreeInput]


def _vector(value: object) -> Vector | None:
    return np.asarray(value, dtype=np.float32) if value is not None else None


# --- From the database (the scoring pipeline) ------------------------------------------------


def load_job_skills(session: Session, job_id: uuid.UUID) -> list[JobSkillInput]:
    rows = session.execute(
        select(JobSkill, Skill)
        .join(Skill, Skill.id == JobSkill.skill_id)
        .where(JobSkill.job_id == job_id)
        .order_by(JobSkill.requirement_type, Skill.canonical_name)
    ).all()
    return [
        JobSkillInput(
            skill_id=skill.id,
            name=skill.canonical_name,
            category=skill.category,
            requirement_type=job_skill.requirement_type,
            weight=float(job_skill.weight),
            min_years=float(job_skill.min_years) if job_skill.min_years is not None else None,
            vector=_vector(skill.embedding),
            is_custom=skill.is_custom,
        )
        for job_skill, skill in rows
    ]


def load_requirements(
    session: Session, job_id: uuid.UUID
) -> tuple[list[RequirementInput], Vector | None]:
    """A job's requirement sentences (in JD order) and its whole-JD vector."""
    rows = session.scalars(
        select(JobRequirement)
        .where(JobRequirement.job_id == job_id)
        .order_by(JobRequirement.position)
    ).all()
    requirements = [
        RequirementInput(
            r.id, r.text, r.category, r.requirement_type, np.asarray(r.embedding, np.float32)
        )
        for r in rows
    ]
    job_vector = session.scalar(select(Job.embedding).where(Job.id == job_id))
    return requirements, _vector(job_vector)


def load_candidate(session: Session, resume_id: uuid.UUID) -> CandidateData:
    """A parsed resume's skills, its chunks (every section), its text and its vector."""
    resume = session.get(Resume, resume_id)
    if resume is None:
        raise LookupError(f"no resume {resume_id}")
    terms: dict[str, list[str]] = (resume.parsed_json or {}).get("skill_terms", {})
    skill_rows = session.execute(
        select(ResumeSkill, Skill)
        .join(Skill, Skill.id == ResumeSkill.skill_id)
        .where(ResumeSkill.resume_id == resume_id)
    ).all()
    skills = [
        CandidateSkillInput(
            skill_id=skill.id,
            name=skill.canonical_name,
            category=skill.category,
            terms=tuple(terms.get(skill.canonical_name, [])),
            years_used=float(rs.years_used) if rs.years_used is not None else None,
            evidence=rs.evidence,
            vector=_vector(skill.embedding),
        )
        for rs, skill in skill_rows
    ]
    chunks = session.scalars(
        select(ResumeChunk)
        .where(ResumeChunk.resume_id == resume_id)
        .order_by(ResumeChunk.chunk_index)
    ).all()
    passages = [Passage(c.section, c.text, np.asarray(c.embedding, np.float32)) for c in chunks]
    roles = [
        RoleInput(
            title=w.job_title,
            company=w.company,
            start=w.start_date,
            end=w.end_date,
            is_current=w.is_current,
            is_internship=is_internship_title(w.job_title),
            vector=_vector(w.embedding),
        )
        for w in session.scalars(
            select(WorkExperience)
            .where(WorkExperience.resume_id == resume_id)
            .order_by(WorkExperience.id)
        )
    ]
    stated = (resume.parsed_json or {}).get("experience_source") == "summary_statement"
    return CandidateData(
        skills=skills,
        passages=passages,
        text=resume.raw_text or "",
        vector=_vector(resume.embedding),
        roles=roles,
        total_months=resume.total_experience_months,
        stated_months=resume.total_experience_months if stated else None,
        degrees=[
            DegreeInput(e.degree_raw, e.degree_level, e.field_of_study)
            for e in session.scalars(
                select(Education).where(Education.resume_id == resume_id).order_by(Education.id)
            )
        ],
    )


# --- Straight from the parsers (tests, evaluation scripts) -------------------------------


def skill_vectors(names: Sequence[str], encoder: TextEncoder) -> dict[str, Vector]:
    """Taxonomy skills' "Name (category)" vectors, as seed_skills.py stores them."""
    taxonomy = {s.name: s for s in get_taxonomy().skills}
    texts = [skill_embedding_text(n, taxonomy[n].category.value) for n in names]
    return dict(zip(names, encoder.encode(texts), strict=True)) if texts else {}


def job_skills_from_parse(parsed: JobParse, vectors: dict[str, Vector]) -> list[JobSkillInput]:
    taxonomy = {s.name: s for s in get_taxonomy().skills}
    return [
        JobSkillInput(
            skill_id=index,
            name=s.name,
            category=taxonomy[s.name].category.value,
            requirement_type=s.requirement_type,
            weight=s.default_weight,
            min_years=s.min_years,
            vector=vectors.get(s.name),
        )
        for index, s in enumerate(parsed.skills)
    ]


def candidate_from_parse(
    parsed: ParsedResume,
    chunks: Sequence[Chunk],
    chunk_vectors: np.ndarray,
    vectors: dict[str, Vector],
    job_skills: Sequence[JobSkillInput],
) -> tuple[list[CandidateSkillInput], list[Passage]]:
    """Ids follow `job_skills` (by name), so the same skill gets the same id on both sides."""
    taxonomy = {s.name: s for s in get_taxonomy().skills}
    ids = {s.name: s.skill_id for s in job_skills}
    next_id = max(ids.values(), default=0) + 1000
    skills = []
    for offset, found in enumerate(parsed.skills.skills):
        months = parsed.skill_months.get(found.name)
        skills.append(
            CandidateSkillInput(
                skill_id=ids.get(found.name, next_id + offset),
                name=found.name,
                category=taxonomy[found.name].category.value,
                terms=found.terms,
                years_used=round(months / 12, 1) if months else None,
                evidence=found.evidence,
                vector=vectors.get(found.name),
            )
        )
    passages = [Passage(c.section, c.text, v) for c, v in zip(chunks, chunk_vectors, strict=True)]
    return skills, passages


def requirements_from_parse(parsed: JobParse, vectors: np.ndarray) -> list[RequirementInput]:
    return [
        RequirementInput(None, r.text, r.category, r.requirement_type, v)
        for r, v in zip(parsed.requirements, vectors, strict=True)
    ]


def roles_from_parse(
    parsed: ParsedResume, role_vectors: Sequence[Vector | None]
) -> list[RoleInput]:
    return [
        RoleInput(
            title=role.title,
            company=role.company,
            start=role.dates.start.as_date() if role.dates else None,
            end=role.dates.end.as_date() if role.dates and role.dates.end else None,
            is_current=role.is_current,
            is_internship=role.is_internship,
            vector=vector,
        )
        for role, vector in zip(parsed.work.roles, role_vectors, strict=True)
    ]


def degrees_from_parse(parsed: ParsedResume) -> list[DegreeInput]:
    return [
        DegreeInput(e.degree, int(e.level) if e.level is not None else None, e.field)
        for e in parsed.education.entries
    ]


def candidate_data_from_parse(
    parsed: ParsedResume,
    chunks: Sequence[Chunk],
    vectors: ResumeVectors,
    skill_vecs: dict[str, Vector],
    job_skills: Sequence[JobSkillInput],
) -> CandidateData:
    """What `load_candidate` would return once this resume is saved (tests, evaluation)."""
    skills, passages = candidate_from_parse(parsed, chunks, vectors.chunks, skill_vecs, job_skills)
    work = parsed.work
    return CandidateData(
        skills=skills,
        passages=passages,
        text="",
        vector=vectors.document,
        roles=roles_from_parse(parsed, vectors.roles),
        total_months=work.total_months,
        stated_months=work.total_months if work.source == "summary_statement" else None,
        degrees=degrees_from_parse(parsed),
    )
