"""Read stored match results: the job's ranking and one candidate's analysis."""

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models import Candidate, MatchResult, Resume

RankingSort = Literal["score", "name", "relevant_experience", "total_experience"]


@dataclass(frozen=True)
class RankingRecord:
    rank: int | None
    resume_id: uuid.UUID
    name: str | None
    email: str | None
    phone: str | None
    filename: str
    current_title: str | None
    total_months: int | None
    relevant_months: int | None
    overall_score: Decimal
    verdict: str | None
    skill_score: Decimal | None
    semantic_score: Decimal | None
    experience_score: Decimal | None
    education_score: Decimal | None
    required_skill_coverage: Decimal | None
    matched_skills: list[dict[str, Any]]
    missing_skills: list[dict[str, Any]]
    is_stale: bool


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _ranking_query(job_id: uuid.UUID) -> Select[*tuple[Any, ...]]:
    """Only the columns the table shows: no explanation, requirement matches or text."""
    return (
        select(
            MatchResult.rank,
            MatchResult.resume_id,
            Candidate.full_name,
            Candidate.email,
            Candidate.phone,
            Resume.original_filename,
            Resume.current_title,
            Resume.total_experience_months,
            MatchResult.relevant_experience_months,
            MatchResult.overall_score,
            MatchResult.explanation["verdict"].astext,
            MatchResult.skill_score,
            MatchResult.semantic_score,
            MatchResult.experience_score,
            MatchResult.education_score,
            MatchResult.required_skill_coverage,
            MatchResult.matched_skills,
            MatchResult.missing_skills,
            MatchResult.is_stale,
        )
        .join(Resume, Resume.id == MatchResult.resume_id)
        .outerjoin(Candidate, Candidate.id == Resume.candidate_id)
        .where(MatchResult.job_id == job_id)
    )


def rankings(
    session: Session,
    job_id: uuid.UUID,
    *,
    min_score: float | None = None,
    skill: str | None = None,
    search: str | None = None,
    sort: RankingSort = "score",
) -> list[RankingRecord]:
    """The job's scored candidates. `skill` is a canonical skill name, matched at any tier."""
    query = _ranking_query(job_id)
    if min_score is not None:
        query = query.where(MatchResult.overall_score >= min_score)
    if skill is not None:  # jsonb containment: [{"skill": "Java", ...}] @> [{"skill": "Java"}]
        query = query.where(MatchResult.matched_skills.contains([{"skill": skill}]))
    if search:
        pattern = f"%{_escape_like(search.strip())}%"
        query = query.where(
            or_(
                Candidate.full_name.ilike(pattern, escape="\\"),
                Resume.original_filename.ilike(pattern, escape="\\"),
                Resume.current_title.ilike(pattern, escape="\\"),
            )
        )
    by_rank = MatchResult.rank.asc().nulls_last()
    order = {
        "score": [by_rank],
        "name": [func.lower(Candidate.full_name).asc().nulls_last(), by_rank],
        "relevant_experience": [
            MatchResult.relevant_experience_months.desc().nulls_last(),
            by_rank,
        ],
        "total_experience": [Resume.total_experience_months.desc().nulls_last(), by_rank],
    }[sort]
    return [RankingRecord(*row) for row in session.execute(query.order_by(*order)).all()]


def candidate_match(
    session: Session, job_id: uuid.UUID, resume_id: uuid.UUID
) -> tuple[MatchResult, Resume, Candidate | None] | None:
    row = session.execute(
        select(MatchResult, Resume, Candidate)
        .join(Resume, Resume.id == MatchResult.resume_id)
        .outerjoin(Candidate, Candidate.id == Resume.candidate_id)
        .where(MatchResult.job_id == job_id, MatchResult.resume_id == resume_id)
    ).one_or_none()
    return (row[0], row[1], row[2]) if row else None
