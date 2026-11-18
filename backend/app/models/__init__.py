"""ORM models. Importing this package registers every table on Base.metadata,
which Alembic autogenerate relies on."""

from app.models.base import EMBEDDING_DIM, Base
from app.models.job import Job, JobRequirement, JobSkill
from app.models.skill import Skill

__all__ = ["EMBEDDING_DIM", "Base", "Job", "JobRequirement", "JobSkill", "Skill"]
