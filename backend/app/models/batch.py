import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import BatchStatus, batch_status_type
from app.models.job import Job

if TYPE_CHECKING:
    from app.models.resume import Resume


class UploadBatch(Base):
    """One upload action: the files a recruiter dropped in at once for a job."""

    __tablename__ = "upload_batches"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    # Files accepted at upload. Files rejected at upload never get a row.
    total_files: Mapped[int]
    processed_files: Mapped[int] = mapped_column(server_default=text("0"))  # parsed successfully
    failed_files: Mapped[int] = mapped_column(server_default=text("0"))
    status: Mapped[BatchStatus] = mapped_column(
        batch_status_type, server_default=BatchStatus.PROCESSING.value
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    job: Mapped[Job] = relationship(lazy="raise")
    resumes: Mapped[list["Resume"]] = relationship(
        back_populates="batch", passive_deletes=True, lazy="raise"
    )

    __table_args__ = (
        CheckConstraint("total_files >= 1", name="total_files_positive"),
        CheckConstraint("processed_files >= 0 AND failed_files >= 0", name="counts_non_negative"),
        CheckConstraint(
            "processed_files + failed_files <= total_files", name="counts_within_total"
        ),
        # The status can never contradict the counts or the completion time.
        CheckConstraint(
            "(status = 'processing') = (completed_at IS NULL)", name="completed_at_matches_status"
        ),
        CheckConstraint(
            "status = 'processing' OR processed_files + failed_files = total_files",
            name="finished_means_all_counted",
        ),
        CheckConstraint(
            "status <> 'completed' OR failed_files = 0", name="completed_has_no_failures"
        ),
        CheckConstraint(
            "status <> 'completed_with_errors' OR failed_files > 0",
            name="completed_with_errors_has_failures",
        ),
    )

    def __repr__(self) -> str:
        return f"UploadBatch(id={self.id!r}, status={self.status!r})"
