"""Bodies for scoring, rankings, candidate detail and weights (design doc §8)."""

import uuid
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

RankingSort = Literal["score", "name", "relevant_experience", "total_experience"]


class Weights(BaseModel):
    """Relative weights: each >= 0, at least one above 0. They need not sum to 1."""

    model_config = ConfigDict(extra="forbid")

    skills: float = Field(ge=0, le=100)
    semantic: float = Field(ge=0, le=100)
    experience: float = Field(ge=0, le=100)
    education: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def _not_all_zero(self) -> Self:
        if self.skills + self.semantic + self.experience + self.education <= 0:
            raise ValueError("at least one weight must be above 0")
        return self


class MatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weights: Weights | None = Field(default=None, description="Saved on the job before scoring")


class MatchRunOut(BaseModel):
    job_id: uuid.UUID
    scored: int = Field(description="Parsed resumes scored")
    weights: dict[str, float]


class RankingRow(BaseModel):
    rank: int | None
    resume_id: uuid.UUID
    name: str | None
    filename: str
    current_title: str | None
    total_years: float | None
    relevant_years: float | None
    match_percent: float
    verdict: str | None
    skill_score: float | None
    semantic_score: float | None
    experience_score: float | None
    education_score: float | None
    required_skill_coverage: float | None
    top_matched_skills: list[str] = Field(description="Up to 5, full credit first")
    matched_skill_count: int = Field(description="All matched skills, at any tier")
    missing_required_count: int
    is_stale: bool = Field(description="The job's requirements changed since this was scored")
    parse_confidence: float | None
    needs_review: bool = Field(description="Parse confidence below 0.5: check the resume by hand")


class RankingsOut(BaseModel):
    job_id: uuid.UUID
    total: int
    rows: list[RankingRow]


class CandidateOut(BaseModel):
    """Everything the candidate page shows, read from what scoring stored."""

    job_id: uuid.UUID
    resume_id: uuid.UUID
    rank: int | None
    match_percent: float
    is_stale: bool
    scoring_version: str
    weights_used: dict[str, float]
    # The person and the parse
    name: str | None
    email: str | None
    phone: str | None
    location: str | None
    linkedin_url: str | None
    github_url: str | None
    filename: str
    current_title: str | None
    total_years: float | None
    relevant_years: float | None
    parse_confidence: float | None
    # The analysis
    component_scores: dict[str, float | None]
    required_skill_coverage: float | None
    matched_skills: list[dict[str, Any]]
    missing_skills: list[dict[str, Any]]
    requirement_matches: list[dict[str, Any]]
    explanation: dict[str, Any] = Field(
        description="verdict, summary, breakdown, strengths, gaps, notes, details"
    )


class WeightsOut(BaseModel):
    job_id: uuid.UUID
    weights: dict[str, float]
    scored: int = Field(description="Resumes rescored with the new weights")
