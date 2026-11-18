"""Load what the skill matcher needs, from the database or straight from the parsers."""

import uuid
from collections.abc import Sequence

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import JobSkill, Resume, ResumeChunk, ResumeSkill, Skill
from app.repositories.skills import skill_embedding_text
from app.services.matching.skills import CandidateSkillInput, JobSkillInput, Passage
from app.services.nlp.embedder import TextEncoder
from app.services.nlp.taxonomy import get_taxonomy
from app.services.nlp.vectors import Vector
from app.services.parsing.chunker import Chunk
from app.services.parsing.jd_parser import JobParse
from app.services.parsing.resume_parser import ParsedResume

# Only described work counts as context for tier 4, not the summary (§6.2).
CONTEXT_SECTIONS = ("experience", "projects")


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


def load_candidate(
    session: Session, resume_id: uuid.UUID
) -> tuple[list[CandidateSkillInput], list[Passage], str]:
    """A parsed resume's skills, its experience/project chunks, and its text."""
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
        .where(ResumeChunk.resume_id == resume_id, ResumeChunk.section.in_(CONTEXT_SECTIONS))
        .order_by(ResumeChunk.chunk_index)
    ).all()
    passages = [Passage(c.section, c.text, np.asarray(c.embedding, np.float32)) for c in chunks]
    return skills, passages, resume.raw_text or ""


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
    passages = [
        Passage(c.section, c.text, v)
        for c, v in zip(chunks, chunk_vectors, strict=True)
        if c.section in CONTEXT_SECTIONS
    ]
    return skills, passages
