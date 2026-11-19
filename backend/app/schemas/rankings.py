"""Bodies for scoring, rankings, candidate detail and weights (design doc §8)."""

import uuid
from typing import Literal, Self

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


class UnrankedOut(BaseModel):
    resume_id: uuid.UUID
    filename: str
    parse_status: Literal["queued", "parsing", "failed"]
    parse_error: str | None = Field(description="Why the file couldn't be read")


class RankingsOut(BaseModel):
    job_id: uuid.UUID
    total: int
    rows: list[RankingRow]
    not_ranked: list[UnrankedOut] = Field(
        description="The job's resumes still being parsed or that failed; filters don't apply"
    )


# --- The stored analysis (match_results JSONB), typed for the candidate page ---------------

RequirementTypeOut = Literal["required", "preferred"]


class MatchedSkillOut(BaseModel):
    skill: str
    requirement_type: RequirementTypeOut
    weight: float
    tier: Literal["exact", "alias", "related", "contextual"]
    credit: float = Field(description="0–1 before any years shortfall")
    matched_skill: str | None = Field(description="The resume skill a related match came from")
    similarity: float | None
    evidence: str | None
    min_years: float | None
    years_used: float | None


class MissingSkillOut(BaseModel):
    skill: str
    requirement_type: RequirementTypeOut
    weight: float


class RequirementMatchOut(BaseModel):
    requirement_id: int
    text: str
    requirement_type: RequirementTypeOut
    similarity: float
    status: Literal["covered", "partial", "not_covered"]
    evidence: str | None = Field(description="The resume sentence closest to the requirement")
    evidence_section: str | None


class BreakdownOut(BaseModel):
    component: Literal["skills", "semantic", "experience", "education"]
    label: str
    active: bool = Field(description="False when there was nothing to score it on")
    score: float | None
    weight: float
    available: float = Field(description="Points this component can give")
    earned: float
    lost: float


class EvidenceItemOut(BaseModel):
    type: str
    impact: float = Field(description="Points: positive earned, negative lost")
    message: str
    snippet: str | None
    section: str | None


class RoleOut(BaseModel):
    title: str | None
    company: str | None
    start: str | None
    end: str | None = Field(description="None while the role is current")
    months: int | None
    similarity: float | None = Field(description="Role title and duties against the JD")
    factor: float = Field(description="How much of the role counts as relevant: 1, 0.5 or 0")
    counted: bool


class ExperienceDetailsOut(BaseModel):
    relevant_months: float
    total_months: int | None
    min_years: float | None
    max_years: float | None
    above_max: bool
    roles: list[RoleOut]


class EducationDetailsOut(BaseModel):
    required_level: int | None
    candidate_level: int | None
    level_score: float | None = Field(description="None when the JD names no degree")
    required_fields: list[str]
    field_result: Literal["not_required", "match", "different", "unknown"]
    candidate_field: str | None
    matched_field: str | None
    weight_factor: float
    waived_by_experience: bool


class SkillCountsOut(BaseModel):
    required_matched: int
    required_total: int


class DetailsOut(BaseModel):
    skills: SkillCountsOut
    experience: ExperienceDetailsOut
    education: EducationDetailsOut


class ExplanationOut(BaseModel):
    verdict: str
    score: float = Field(description="The breakdown's earned points summed; equals the match %")
    summary: str
    breakdown: list[BreakdownOut]
    strengths: list[EvidenceItemOut]
    gaps: list[EvidenceItemOut]
    notes: list[str]
    details: DetailsOut


class EducationOut(BaseModel):
    degree: str | None = Field(description="As written on the resume")
    degree_level: int | None = Field(description="0 none … 5 doctorate")
    field_of_study: str | None
    institution: str | None
    graduation_year: int | None


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
    needs_review: bool = Field(description="Parse confidence below 0.5: check the resume by hand")
    educations: list[EducationOut]
    raw_text: str | None = Field(description="The text extracted from the file")
    # The analysis
    component_scores: dict[str, float | None]
    required_skill_coverage: float | None
    matched_skills: list[MatchedSkillOut]
    missing_skills: list[MissingSkillOut]
    requirement_matches: list[RequirementMatchOut]
    explanation: ExplanationOut


class WeightsOut(BaseModel):
    job_id: uuid.UUID
    weights: dict[str, float]
    scored: int = Field(description="Resumes rescored with the new weights")
