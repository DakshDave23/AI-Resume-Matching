"""Small builders for valid rows; tests override only the fields they care about."""

import hashlib
import uuid
from decimal import Decimal
from typing import Any

from app.models import EMBEDDING_DIM, Job, JobRequirement, MatchResult, Resume, UploadBatch
from app.models.enums import FileType, RequirementCategory, RequirementType
from app.services.matching.scoring_config import DEFAULT_WEIGHTS

VECTOR = [0.0] * (EMBEDDING_DIM - 1) + [1.0]


def make_job(**overrides: Any) -> Job:
    fields: dict[str, Any] = {"title": "Backend Java Developer", "raw_text": "We need Java."}
    return Job(**(fields | overrides))


def make_requirement(position: int = 0) -> JobRequirement:
    return JobRequirement(
        text="Design and build scalable backend services",
        category=RequirementCategory.RESPONSIBILITY,
        requirement_type=RequirementType.REQUIRED,
        position=position,
        embedding=VECTOR,
    )


def make_batch(job: Job | None = None, **overrides: Any) -> UploadBatch:
    fields: dict[str, Any] = {"job": job or make_job(), "total_files": 1}
    return UploadBatch(**(fields | overrides))


def make_resume(batch: UploadBatch, **overrides: Any) -> Resume:
    fields: dict[str, Any] = {
        "batch": batch,
        "original_filename": "resume.pdf",
        "storage_path": f"{uuid.uuid4()}.pdf",
        "file_type": FileType.PDF,
        "file_size_bytes": 120_000,
        "file_sha256": hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
    }
    return Resume(**(fields | overrides))


def make_match(job: Job, resume: Resume, **overrides: Any) -> MatchResult:
    fields: dict[str, Any] = {
        "job": job,
        "resume": resume,
        "overall_score": Decimal("83.10"),
        "skill_score": Decimal("0.731"),
        "weights_used": DEFAULT_WEIGHTS,
        "scoring_version": "v1.0",
    }
    return MatchResult(**(fields | overrides))
