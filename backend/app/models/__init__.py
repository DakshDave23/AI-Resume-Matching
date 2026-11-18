"""ORM models. Importing this package registers every table on Base.metadata,
which Alembic autogenerate relies on."""

from app.models.base import EMBEDDING_DIM, Base
from app.models.batch import UploadBatch
from app.models.candidate import Candidate
from app.models.job import Job, JobRequirement, JobSkill
from app.models.match import MatchResult
from app.models.resume import Education, Resume, ResumeChunk, ResumeSkill, WorkExperience
from app.models.skill import Skill

__all__ = [
    "EMBEDDING_DIM",
    "Base",
    "Candidate",
    "Education",
    "Job",
    "JobRequirement",
    "JobSkill",
    "MatchResult",
    "Resume",
    "ResumeChunk",
    "ResumeSkill",
    "Skill",
    "UploadBatch",
    "WorkExperience",
]
