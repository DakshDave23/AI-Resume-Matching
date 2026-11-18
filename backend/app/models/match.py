import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.job import Job
from app.models.resume import Resume

_EMPTY_LIST = text("'[]'::jsonb")
_EMPTY_OBJECT = text("'{}'::jsonb")


class MatchResult(Base):
    """One scored (job, resume) pair: the stored snapshot of a scoring run.

    Rescoring upserts on (job_id, resume_id). JSONB columns are always read
    together and keep past explanations stable if the taxonomy changes later.
    """

    __tablename__ = "match_results"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    resume_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resumes.id", ondelete="CASCADE"), index=True
    )

    overall_score: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    # Each 0-1; null when the component is inactive for this job (design doc §6.1).
    skill_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    semantic_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    experience_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    education_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    required_skill_coverage: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    relevant_experience_months: Mapped[int | None]

    matched_skills: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default=_EMPTY_LIST)
    missing_skills: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default=_EMPTY_LIST)
    requirement_matches: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, server_default=_EMPTY_LIST
    )
    explanation: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=_EMPTY_OBJECT)
    weights_used: Mapped[dict[str, float]] = mapped_column(JSONB)
    scoring_version: Mapped[str] = mapped_column(String(20))

    rank: Mapped[int | None]  # position within the job, assigned after the whole batch is scored
    # Set when the job's requirements change after scoring (PATCH /requirements).
    is_stale: Mapped[bool] = mapped_column(server_default=false())
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    job: Mapped[Job] = relationship(lazy="raise")
    resume: Mapped[Resume] = relationship(lazy="raise")

    __table_args__ = (
        UniqueConstraint("job_id", "resume_id"),
        # Serves the ranking table directly: WHERE job_id = ? ORDER BY overall_score DESC.
        Index("ix_match_results_job_id_score", "job_id", text("overall_score DESC")),
        CheckConstraint("overall_score BETWEEN 0 AND 100", name="overall_score_range"),
        CheckConstraint(
            "skill_score BETWEEN 0 AND 1 AND semantic_score BETWEEN 0 AND 1 "
            "AND experience_score BETWEEN 0 AND 1 AND education_score BETWEEN 0 AND 1",
            name="component_scores_range",
        ),
        CheckConstraint("required_skill_coverage BETWEEN 0 AND 1", name="coverage_range"),
        CheckConstraint("relevant_experience_months >= 0", name="relevant_months_non_negative"),
        CheckConstraint("rank >= 1", name="rank_positive"),
    )

    def __repr__(self) -> str:
        return f"MatchResult(job_id={self.job_id!r}, resume_id={self.resume_id!r})"
