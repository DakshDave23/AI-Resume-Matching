from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, Identity, Index, String, Text, false, func, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import EMBEDDING_DIM, Base
from app.models.enums import SkillCategory

_CATEGORY_LIST = ", ".join(f"'{c.value}'" for c in SkillCategory)


class Skill(Base):
    """The curated skills taxonomy (seeded from skills_taxonomy.json in step 6).

    Shared by jobs and resumes, so it never cascades: a skill still referenced
    by a job or resume cannot be deleted.
    """

    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(40))  # a SkillCategory value
    aliases: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    # Canonical name + short description; filled at seed time once the model is available.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    is_custom: Mapped[bool] = mapped_column(server_default=false())

    __table_args__ = (
        # Case-insensitive uniqueness: "PostgreSQL" and "postgresql" are the same skill.
        Index("uq_skills_canonical_name_lower", func.lower(canonical_name), unique=True),
        Index("ix_skills_aliases", aliases, postgresql_using="gin"),
        CheckConstraint("length(btrim(canonical_name)) > 0", name="canonical_name_not_blank"),
        # VARCHAR + CHECK rather than a Postgres ENUM: adding a category later is a
        # one-line constraint swap, not an ALTER TYPE.
        CheckConstraint(f"category IN ({_CATEGORY_LIST})", name="category_valid"),
    )

    def __repr__(self) -> str:
        return f"Skill(id={self.id!r}, canonical_name={self.canonical_name!r})"
