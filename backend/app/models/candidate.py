import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Candidate(Base):
    """The person behind one or more resumes, deduplicated by email.

    Shared across jobs, so it never cascades. Location is shown in the UI but
    never used in scoring (design doc §14, "Is it fair?").
    """

    __tablename__ = "candidates"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    full_name: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(254))
    phone: Mapped[str | None] = mapped_column(String(30))  # E.164, e.g. +919876543210
    location: Mapped[str | None] = mapped_column(String(200))
    linkedin_url: Mapped[str | None] = mapped_column(Text)
    github_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        # One candidate per email, ignoring case; many candidates may have no email.
        Index(
            "uq_candidates_email_lower",
            func.lower(email),
            unique=True,
            postgresql_where=text("email IS NOT NULL"),
        ),
        CheckConstraint("position('@' in email) > 1", name="email_has_at"),
        CheckConstraint(r"phone ~ '^\+[1-9][0-9]{6,14}$'", name="phone_e164"),
    )

    def __repr__(self) -> str:
        return f"Candidate(id={self.id!r}, full_name={self.full_name!r})"
