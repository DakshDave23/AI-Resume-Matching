import json
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import EMBEDDING_DIM, Base
from app.models.enums import (
    JobStatus,
    RequirementCategory,
    RequirementType,
    SkillAddedBy,
    job_status_type,
    requirement_category_type,
    requirement_type_type,
)
from app.models.skill import Skill
from app.services.matching.scoring_config import DEFAULT_WEIGHTS

# Relationships use lazy="raise": repositories must load related rows explicitly
# (selectinload/joinedload), so an accidental N+1 query fails loudly in tests.


class Job(Base):
    """One job description."""

    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    title: Mapped[str] = mapped_column(String(200))
    company: Mapped[str | None] = mapped_column(String(200))
    raw_text: Mapped[str] = mapped_column(Text)
    source_filename: Mapped[str | None] = mapped_column(String(255))  # null when pasted

    min_experience_years: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    max_experience_years: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    required_degree_level: Mapped[int | None] = mapped_column(SmallInteger)  # DegreeLevel
    required_fields_of_study: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=text("'{}'")
    )
    # "Bachelor's or equivalent experience": halves the education weight (design doc §5.4, §6.5).
    accepts_equivalent_experience: Mapped[bool] = mapped_column(server_default=false())

    scoring_weights: Mapped[dict[str, float]] = mapped_column(
        JSONB, server_default=text(f"'{json.dumps(DEFAULT_WEIGHTS)}'::jsonb")
    )
    parsed_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # full extractor output
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    status: Mapped[JobStatus] = mapped_column(job_status_type, server_default=JobStatus.DRAFT.value)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    requirements: Mapped[list["JobRequirement"]] = relationship(
        back_populates="job",
        order_by="JobRequirement.position",
        cascade="all, delete-orphan",
        passive_deletes=True,  # let ON DELETE CASCADE do the work in the DB
        lazy="raise",
    )
    skills: Mapped[list["JobSkill"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="raise",
    )

    __table_args__ = (
        CheckConstraint("length(btrim(title)) > 0", name="title_not_blank"),
        CheckConstraint("min_experience_years >= 0", name="min_experience_non_negative"),
        CheckConstraint(
            "max_experience_years >= min_experience_years", name="max_experience_gte_min"
        ),
        CheckConstraint("max_experience_years >= 0", name="max_experience_non_negative"),
        CheckConstraint("required_degree_level BETWEEN 0 AND 5", name="degree_level_range"),
    )

    def __repr__(self) -> str:
        return f"Job(id={self.id!r}, title={self.title!r}, status={self.status!r})"


class JobRequirement(Base):
    """One requirement or responsibility sentence from a JD, embedded for semantic coverage."""

    __tablename__ = "job_requirements"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    text: Mapped[str] = mapped_column(Text)
    category: Mapped[RequirementCategory] = mapped_column(requirement_category_type)
    requirement_type: Mapped[RequirementType] = mapped_column(requirement_type_type)
    position: Mapped[int] = mapped_column(SmallInteger)  # order in the JD
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))

    job: Mapped[Job] = relationship(back_populates="requirements", lazy="raise")

    __table_args__ = (
        # Also serves as the job_id index (job_id is the leading column).
        UniqueConstraint("job_id", "position"),
        CheckConstraint("position >= 0", name="position_non_negative"),
        CheckConstraint("length(btrim(text)) > 0", name="text_not_blank"),
    )

    def __repr__(self) -> str:
        return f"JobRequirement(id={self.id!r}, position={self.position!r})"


class JobSkill(Base):
    """Bridge: a skill a job requires or prefers."""

    __tablename__ = "job_skills"

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="RESTRICT"), primary_key=True, index=True
    )
    requirement_type: Mapped[RequirementType] = mapped_column(requirement_type_type)
    # 1.00 for required, 0.50 for preferred; set by the service layer.
    weight: Mapped[Decimal] = mapped_column(Numeric(3, 2), server_default=text("1.00"))
    min_years: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))  # "5+ years of Java"
    source_text: Mapped[str | None] = mapped_column(Text)  # the JD phrase it came from
    added_by: Mapped[SkillAddedBy] = mapped_column(
        String(10), server_default=SkillAddedBy.PARSER.value
    )

    job: Mapped[Job] = relationship(back_populates="skills", lazy="raise")
    skill: Mapped[Skill] = relationship(lazy="raise")

    __table_args__ = (
        CheckConstraint("weight > 0 AND weight <= 1", name="weight_range"),
        CheckConstraint("min_years >= 0", name="min_years_non_negative"),
        CheckConstraint("added_by IN ('parser', 'recruiter')", name="added_by_valid"),
    )

    def __repr__(self) -> str:
        return f"JobSkill(job_id={self.job_id!r}, skill_id={self.skill_id!r})"
