"""The match %: four component scores combined (design doc §6.1).

    Score = 100 * sum(w_i * S_i) / sum(w_i)     over the active components only

- A component the JD doesn't ask for drops out and the other weights are rescaled:
  experience without a minimum, education without a degree, skills without skills,
  semantic without requirement sentences.
- "Or equivalent experience" halves education's weight before rescaling.
- Ranking ties are broken by required-skill coverage, then relevant experience
  (done in SQL, see repositories/matches.py).

`ScoringJob` holds everything about a job that every resume is compared with,
computed once per job: its skills, requirement vectors, role profile.
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Job
from app.models.enums import RequirementCategory
from app.services.matching import scoring_config as config
from app.services.matching.education import EducationScore, education_score
from app.services.matching.experience import ExperienceScore, experience_score, role_profile
from app.services.matching.inputs import (
    CandidateData,
    job_skills_from_parse,
    load_job_skills,
    load_requirements,
    requirements_from_parse,
)
from app.services.matching.semantic import RequirementInput, SemanticScore, semantic_score
from app.services.matching.skills import PreparedJob, SkillScore, match_skills, prepare_job
from app.services.nlp.embedder import TextEncoder
from app.services.nlp.vectors import JobVectors, Vector
from app.services.parsing.jd_parser import JobParse


@dataclass(frozen=True)
class ScoringJob:
    job_id: uuid.UUID
    weights: dict[str, float]
    skills: PreparedJob
    requirements: list[RequirementInput]
    job_vector: Vector | None
    profile: Vector
    min_years: float | None
    max_years: float | None
    required_level: int | None
    required_fields: tuple[str, ...]
    accepts_equivalent_experience: bool


@dataclass(frozen=True)
class Combined:
    score: float  # 0-100
    components: dict[str, float | None]  # None: inactive
    effective_weights: dict[str, float]  # rescaled over the active components; sum to 1


@dataclass(frozen=True)
class MatchOutcome:
    combined: Combined
    skills: SkillScore
    semantic: SemanticScore | None
    experience: ExperienceScore
    education: EducationScore
    weights: dict[str, float] = field(default_factory=dict)  # the job's weights, as configured

    @property
    def score(self) -> float:
        return self.combined.score


def combine(
    components: Mapping[str, float | None],
    weights: Mapping[str, float],
    *,
    education_factor: float = 1.0,
) -> Combined:
    """The weighted mean of the active components, x 100.

    Weights are relative (they need not sum to 1). Nothing active, or only zero
    weights, scores 0: there is nothing to match on.
    """
    raw = {name: weights.get(name, 0.0) for name in config.COMPONENTS}
    raw["education"] *= education_factor
    active = {name for name in config.COMPONENTS if components.get(name) is not None}
    total = sum(raw[name] for name in active)
    if total <= 0:
        effective = dict.fromkeys(config.COMPONENTS, 0.0)
        return Combined(0.0, dict(components), effective)
    effective = {name: (raw[name] / total if name in active else 0.0) for name in config.COMPONENTS}
    score = 100 * sum(effective[name] * (components[name] or 0.0) for name in active)
    return Combined(min(100.0, max(0.0, score)), dict(components), effective)


def load_scoring_job(session: Session, job_id: uuid.UUID, encoder: TextEncoder) -> ScoringJob:
    """Everything about a job the scorers need, read and embedded once."""
    job = session.get(Job, job_id)
    if job is None:
        raise LookupError(f"no job {job_id}")
    requirements, job_vector = load_requirements(session, job_id)
    responsibilities = [
        r.text for r in requirements if r.category == RequirementCategory.RESPONSIBILITY
    ]
    if not responsibilities:  # a JD without that section: its other sentences describe the role
        responsibilities = [
            r.text for r in requirements if r.category.value not in config.NOT_SEMANTIC_CATEGORIES
        ]
    return ScoringJob(
        job_id=job.id,
        weights=dict(job.scoring_weights),
        skills=prepare_job(load_job_skills(session, job_id), encoder),
        requirements=requirements,
        job_vector=job_vector,
        profile=role_profile(job.title, responsibilities, encoder),
        min_years=_float(job.min_experience_years),
        max_years=_float(job.max_experience_years),
        required_level=job.required_degree_level,
        required_fields=tuple(job.required_fields_of_study),
        accepts_equivalent_experience=job.accepts_equivalent_experience,
    )


def _float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def score_candidate(
    job: ScoringJob, candidate: CandidateData, *, today: date, encoder: TextEncoder
) -> MatchOutcome:
    skills = match_skills(
        job.skills, candidate.skills, candidate.passages, resume_text=candidate.text
    )
    semantic = semantic_score(
        job.requirements,
        candidate.passages,
        job_vector=job.job_vector,
        resume_vector=candidate.vector,
    )
    experience = experience_score(
        job.profile,
        candidate.roles,
        today=today,
        min_years=job.min_years,
        max_years=job.max_years,
        total_months=candidate.total_months,
        stated_months=candidate.stated_months,
    )
    education = education_score(
        candidate.degrees,
        required_level=job.required_level,
        required_fields=job.required_fields,
        accepts_equivalent_experience=job.accepts_equivalent_experience,
        relevant_years=experience.relevant_years,
        min_years=job.min_years,
        encoder=encoder,
    )
    combined = combine(
        {
            "skills": skills.score,
            "semantic": semantic.score if semantic is not None else None,
            "experience": experience.score,
            "education": education.score,
        },
        job.weights,
        education_factor=education.weight_factor,
    )
    return MatchOutcome(combined, skills, semantic, experience, education, job.weights)


def scoring_job_from_parse(
    parsed: JobParse,
    vectors: JobVectors,
    skill_vecs: dict[str, Vector],
    encoder: TextEncoder,
    *,
    weights: Mapping[str, float] = config.DEFAULT_WEIGHTS,
) -> ScoringJob:
    """What `load_scoring_job` would build once this JD is saved (tests, evaluation)."""
    requirements = requirements_from_parse(parsed, vectors.requirements)
    responsibilities = [
        r.text for r in requirements if r.category == RequirementCategory.RESPONSIBILITY
    ]
    return ScoringJob(
        job_id=uuid.UUID(int=0),
        weights=dict(weights),
        skills=prepare_job(job_skills_from_parse(parsed, skill_vecs), encoder),
        requirements=requirements,
        job_vector=vectors.document,
        profile=role_profile(parsed.title or "", responsibilities, encoder),
        min_years=parsed.min_experience_years,
        max_years=parsed.max_experience_years,
        required_level=parsed.degree_level,
        required_fields=parsed.fields_of_study,
        accepts_equivalent_experience=parsed.accepts_equivalent_experience,
    )
