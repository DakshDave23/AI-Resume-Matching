"""Response bodies for resume uploads (design doc §8)."""

import uuid

from pydantic import BaseModel, Field

from app.models.enums import BatchStatus, ParseStatus


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
