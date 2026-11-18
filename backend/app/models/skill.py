from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, Identity, Index, String, Text, false, func, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import EMBEDDING_DIM, Base


class Skill(Base):
    """The curated skills taxonomy (seeded from skills_taxonomy.json in step 6).

    Shared by jobs and resumes, so it never cascades: a skill still referenced
    by a job or resume cannot be deleted.
    """

    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(100))
    # language, framework, database, cloud, devops, tool, methodology, soft, ...
    # The full list is settled with the taxonomy in step 6.
    category: Mapped[str] = mapped_column(String(40))
    aliases: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    # Canonical name + short description; filled at seed time once the model is available.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    is_custom: Mapped[bool] = mapped_column(server_default=false())

    __table_args__ = (
        # Case-insensitive uniqueness: "PostgreSQL" and "postgresql" are the same skill.
        Index("uq_skills_canonical_name_lower", func.lower(canonical_name), unique=True),
        Index("ix_skills_aliases", aliases, postgresql_using="gin"),
        CheckConstraint("length(btrim(canonical_name)) > 0", name="canonical_name_not_blank"),
        CheckConstraint("length(btrim(category)) > 0", name="category_not_blank"),
    )

    def __repr__(self) -> str:
        return f"Skill(id={self.id!r}, canonical_name={self.canonical_name!r})"
