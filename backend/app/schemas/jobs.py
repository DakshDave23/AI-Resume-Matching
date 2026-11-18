"""Request and response bodies for the job routes (design doc §8)."""

import uuid
from datetime import datetime
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.models.enums import (
    DegreeLevel,
    JobStatus,
    RequirementCategory,
    RequirementType,
    Seniority,
    SkillAddedBy,
    SkillCategory,
)

MAX_JD_CHARS = 100_000
MAX_YEARS = 50.0

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
SkillName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
FieldName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Years = Annotated[float, Field(ge=0, le=MAX_YEARS)]


# --- Requests ---------------------------------------------------------------------------


class JobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title | None = Field(
        default=None, description="Optional; otherwise read from the JD's first line or label"
    )
    text: str = Field(min_length=1, max_length=MAX_JD_CHARS, description="The JD as pasted")

    @model_validator(mode="after")
    def _has_text(self) -> Self:
        if len(self.text.split()) < 3:
            raise ValueError("text is too short to be a job description")
        return self


class SkillRequirementIn(BaseModel):
    """One skill chip: an existing skill (by id or name/alias) or a new custom one."""

    model_config = ConfigDict(extra="forbid")

    skill_id: int | None = None
    name: SkillName | None = Field(
        default=None, description="Canonical name or alias; an unknown name adds a custom skill"
    )
    category: SkillCategory | None = Field(
        default=None, description="Only used when `name` creates a custom skill (default: tool)"
    )
    requirement_type: RequirementType
    min_years: Years | None = None

    @model_validator(mode="after")
    def _one_reference(self) -> Self:
        if (self.skill_id is None) == (self.name is None):
            raise ValueError("give exactly one of skill_id or name")
        return self


class RequirementsUpdate(BaseModel):
    """Recruiter edits. Only the fields sent are changed; `skills` replaces the whole list."""

    model_config = ConfigDict(extra="forbid")

    skills: list[SkillRequirementIn] | None = Field(default=None, max_length=100)
    min_experience_years: Years | None = None
    max_experience_years: Years | None = None
    required_degree_level: DegreeLevel | None = None
    required_fields_of_study: list[FieldName] | None = Field(default=None, max_length=20)
    accepts_equivalent_experience: bool | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        sent = self.model_fields_set
        for name in ("skills", "accepts_equivalent_experience"):
            if name in sent and getattr(self, name) is None:
                raise ValueError(f"{name} can't be null")
        low, high = self.min_experience_years, self.max_experience_years
        if low is not None and high is not None and high < low:
            raise ValueError("max_experience_years is below min_experience_years")
        return self


# --- Responses --------------------------------------------------------------------------


class JobSkillOut(BaseModel):
    skill_id: int
    name: str
    category: str
    is_custom: bool
    requirement_type: RequirementType
    weight: float
    min_years: float | None
    source_text: str | None
    added_by: SkillAddedBy


class JobRequirementOut(BaseModel):
    id: int
    position: int
    text: str
    category: RequirementCategory
    requirement_type: RequirementType


class JobOut(BaseModel):
    id: uuid.UUID
    title: str
    company: str | None
    location: str | None
    seniority: Seniority | None
    status: JobStatus
    source_filename: str | None
    raw_text: str
    min_experience_years: float | None
    max_experience_years: float | None
    required_degree_level: DegreeLevel | None
    required_fields_of_study: list[str]
    accepts_equivalent_experience: bool
    scoring_weights: dict[str, float]
    skills: list[JobSkillOut] = Field(description="Required first, then preferred")
    unmapped_skills: list[str] = Field(description="JD skill-list items not in the taxonomy")
    requirements: list[JobRequirementOut] = Field(description="In JD order")
    created_at: datetime
    updated_at: datetime


class JobSummaryOut(BaseModel):
    id: uuid.UUID
    title: str
    company: str | None
    status: JobStatus
    created_at: datetime
    resume_count: int
    top_score: float | None = Field(description="Best match %, once resumes are scored")


class JobListOut(BaseModel):
    items: list[JobSummaryOut]
    total: int
    limit: int
    offset: int
