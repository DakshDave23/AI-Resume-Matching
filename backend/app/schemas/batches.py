"""Response bodies for resume uploads (design doc §8)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import BatchStatus, FileType, ParseStatus


class AcceptedFileOut(BaseModel):
    resume_id: uuid.UUID
    filename: str
    size_bytes: int
    parse_status: ParseStatus


class RejectedFileOut(BaseModel):
    filename: str
    code: str = Field(description="e.g. unsupported_type, file_too_large, duplicate_file")
    message: str = Field(description="A reason to show the recruiter")


class BatchCreatedOut(BaseModel):
    batch_id: uuid.UUID
    job_id: uuid.UUID
    status: BatchStatus
    total_files: int = Field(description="Files accepted; rejected files are not counted")
    accepted: list[AcceptedFileOut]
    rejected: list[RejectedFileOut]


class BatchFileOut(BaseModel):
    resume_id: uuid.UUID
    filename: str
    file_type: FileType
    size_bytes: int
    parse_status: ParseStatus
    parse_error: str | None = Field(description="Why parsing failed; only when failed")
    parse_confidence: float | None = Field(description="Share of the six parse checks passed")
    needs_review: bool = Field(description="Parsed, but confidence below 0.5: check it by hand")
    candidate_name: str | None


class BatchStatusOut(BaseModel):
    batch_id: uuid.UUID
    job_id: uuid.UUID
    status: BatchStatus
    total_files: int
    processed_files: int = Field(description="Parsed successfully")
    failed_files: int
    pending_files: int = Field(description="Still queued or parsing")
    created_at: datetime
    completed_at: datetime | None
    files: list[BatchFileOut] = Field(description="Sorted by file name")
