import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
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
)
from sqlalchemy.dialects.postgresql import ARRAY, CHAR, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import EMBEDDING_DIM, Base
from app.models.batch import UploadBatch
from app.models.candidate import Candidate
from app.models.enums import (
    FileType,
    ParseStatus,
    SkillSource,
    file_type_type,
    parse_status_type,
    skill_source_type,
)
from app.models.skill import Skill

# Matches the upload limit in design doc §5.1. Settings.max_file_size_mb is capped
# at 5 for the same reason: raising it means a migration for this CHECK too.
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024

CHUNK_SECTIONS = ("experience", "projects", "summary", "skills")


class Resume(Base):
    """One uploaded document and everything parsed out of it."""

    __tablename__ = "resumes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("upload_batches.id", ondelete="CASCADE"))
    # Null until parsing finds the person. Candidates are shared: never cascade.
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("candidates.id", ondelete="RESTRICT"), index=True
    )

    original_filename: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(Text, unique=True)  # <uuid>.<ext>, never user input
    file_type: Mapped[FileType] = mapped_column(file_type_type)
    file_size_bytes: Mapped[int]
    file_sha256: Mapped[str] = mapped_column(CHAR(64))

    raw_text: Mapped[str | None] = mapped_column(Text)
    sections: Mapped[dict[str, str] | None] = mapped_column(JSONB)  # section name -> text
    parsed_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    total_experience_months: Mapped[int | None]  # union of date ranges, overlaps merged
    highest_degree_level: Mapped[int | None] = mapped_column(SmallInteger)  # DegreeLevel
    current_title: Mapped[str | None] = mapped_column(String(200))

    parse_status: Mapped[ParseStatus] = mapped_column(
        parse_status_type, server_default=ParseStatus.QUEUED.value
    )
    parse_error: Mapped[str | None] = mapped_column(Text)  # human-readable, shown in the UI
    parse_confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    batch: Mapped[UploadBatch] = relationship(back_populates="resumes", lazy="raise")
    candidate: Mapped[Candidate | None] = relationship(lazy="raise")
    skills: Mapped[list["ResumeSkill"]] = relationship(
        back_populates="resume", cascade="all, delete-orphan", passive_deletes=True, lazy="raise"
    )
    work_experiences: Mapped[list["WorkExperience"]] = relationship(
        back_populates="resume",
        order_by="WorkExperience.id",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="raise",
    )
    educations: Mapped[list["Education"]] = relationship(
        back_populates="resume",
        order_by="Education.id",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="raise",
    )
    chunks: Mapped[list["ResumeChunk"]] = relationship(
        back_populates="resume",
        order_by="ResumeChunk.chunk_index",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="raise",
    )

    __table_args__ = (
        # The same file twice in one batch is a 409; this unique index also serves batch_id lookups.
        UniqueConstraint("batch_id", "file_sha256"),
        CheckConstraint(
            f"file_size_bytes > 0 AND file_size_bytes <= {MAX_FILE_SIZE_BYTES}",
            name="file_size_range",
        ),
        CheckConstraint("file_sha256 ~ '^[0-9a-f]{64}$'", name="sha256_hex"),
        CheckConstraint("total_experience_months >= 0", name="experience_non_negative"),
        CheckConstraint("highest_degree_level BETWEEN 0 AND 5", name="degree_level_range"),
        CheckConstraint("parse_confidence BETWEEN 0 AND 1", name="confidence_range"),
        # "failed" always comes with a readable reason, and only "failed" has one.
        CheckConstraint(
            "(parse_status = 'failed') = (parse_error IS NOT NULL)", name="error_iff_failed"
        ),
        CheckConstraint(
            "parse_status <> 'parsed' OR parsed_at IS NOT NULL", name="parsed_has_timestamp"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"Resume(id={self.id!r}, file={self.original_filename!r}, status={self.parse_status!r})"
        )


class ResumeSkill(Base):
    """Bridge: a taxonomy skill found in a resume, with provenance."""

    __tablename__ = "resume_skills"

    resume_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resumes.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="RESTRICT"), primary_key=True, index=True
    )
    sources: Mapped[list[SkillSource]] = mapped_column(ARRAY(skill_source_type))
    mention_count: Mapped[int] = mapped_column(SmallInteger)
    years_used: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    evidence: Mapped[str | None] = mapped_column(Text)  # best supporting snippet

    resume: Mapped[Resume] = relationship(back_populates="skills", lazy="raise")
    skill: Mapped[Skill] = relationship(lazy="raise")

    __table_args__ = (
        CheckConstraint("cardinality(sources) >= 1", name="has_source"),
        CheckConstraint("mention_count >= 1", name="mention_count_positive"),
        CheckConstraint("years_used >= 0", name="years_used_non_negative"),
    )


class WorkExperience(Base):
    __tablename__ = "work_experiences"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    resume_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resumes.id", ondelete="CASCADE"), index=True
    )
    job_title: Mapped[str | None] = mapped_column(String(200))
    company: Mapped[str | None] = mapped_column(String(200))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)  # null while is_current
    is_current: Mapped[bool] = mapped_column(server_default=false())  # "Present", "Till date"
    duration_months: Mapped[int | None]
    description: Mapped[str | None] = mapped_column(Text)  # bullets under the role
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))  # title + desc

    resume: Mapped[Resume] = relationship(back_populates="work_experiences", lazy="raise")

    __table_args__ = (
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="end_after_start"),
        CheckConstraint("NOT is_current OR end_date IS NULL", name="current_has_no_end"),
        CheckConstraint("duration_months >= 0", name="duration_non_negative"),
    )


class Education(Base):
    __tablename__ = "educations"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    resume_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resumes.id", ondelete="CASCADE"), index=True
    )
    degree_raw: Mapped[str | None] = mapped_column(String(200))  # as written, e.g. "B.Tech"
    degree_level: Mapped[int | None] = mapped_column(SmallInteger)  # DegreeLevel
    field_of_study: Mapped[str | None] = mapped_column(String(200))
    institution: Mapped[str | None] = mapped_column(String(200))
    graduation_year: Mapped[int | None] = mapped_column(SmallInteger)

    resume: Mapped[Resume] = relationship(back_populates="educations", lazy="raise")

    __table_args__ = (
        CheckConstraint("degree_level BETWEEN 0 AND 5", name="degree_level_range"),
        CheckConstraint("graduation_year BETWEEN 1950 AND 2100", name="graduation_year_range"),
    )


class ResumeChunk(Base):
    """An embedded passage, used for semantic coverage and as explanation evidence."""

    __tablename__ = "resume_chunks"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    resume_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"))
    section: Mapped[str] = mapped_column(String(30))
    chunk_index: Mapped[int] = mapped_column(SmallInteger)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))

    resume: Mapped[Resume] = relationship(back_populates="chunks", lazy="raise")

    __table_args__ = (
        # Also serves resume_id lookups (leading column).
        UniqueConstraint("resume_id", "chunk_index"),
        CheckConstraint("chunk_index >= 0", name="chunk_index_non_negative"),
        CheckConstraint(
            "section IN (" + ", ".join(f"'{s}'" for s in CHUNK_SECTIONS) + ")",
            name="section_valid",
        ),
        CheckConstraint("length(btrim(text)) > 0", name="text_not_blank"),
    )
