"""Database reads and writes for the skills taxonomy."""

from dataclasses import dataclass

from sqlalchemy import func, literal_column, or_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from sqlalchemy.sql.dml import ReturningInsert

from app.models import Skill
from app.services.nlp.taxonomy import Taxonomy


@dataclass(frozen=True)
class SeedResult:
    inserted: int
    updated: int
    unchanged: int


def upsert_taxonomy(session: Session, taxonomy: Taxonomy) -> SeedResult:
    """Insert or update every taxonomy skill in one statement. Safe to run repeatedly.

    - Matches existing rows case-insensitively, via the unique index on lower(canonical_name).
    - Rows that already match the file are left untouched (and counted as unchanged).
    - A recruiter-added custom skill that the taxonomy now covers becomes a regular skill.
    - Skills missing from the file are never deleted: jobs and resumes may reference them.
    - Embeddings are not touched here; they are computed separately (step 17).
    """
    if not taxonomy.skills:
        return SeedResult(0, 0, 0)

    rows = [
        {
            "canonical_name": s.name,
            "category": s.category.value,
            "aliases": list(s.aliases),
            "is_custom": False,
        }
        for s in taxonomy.skills
    ]
    insert_stmt = insert(Skill).values(rows)
    new = insert_stmt.excluded
    upsert: ReturningInsert[tuple[bool]] = insert_stmt.on_conflict_do_update(
        index_elements=[func.lower(Skill.canonical_name)],
        set_={
            "canonical_name": new.canonical_name,
            "category": new.category,
            "aliases": new.aliases,
            "is_custom": False,
        },
        # Skip the write entirely when nothing changed.
        where=or_(
            Skill.canonical_name.is_distinct_from(new.canonical_name),
            Skill.category.is_distinct_from(new.category),
            Skill.aliases.is_distinct_from(new.aliases),
            Skill.is_custom,
        ),
    ).returning(
        # xmax = 0 only for freshly inserted rows; updated rows have it set.
        literal_column("xmax = 0").label("inserted")
    )

    written = session.execute(upsert).scalars().all()
    inserted = sum(1 for was_insert in written if was_insert)
    updated = len(written) - inserted
    return SeedResult(inserted=inserted, updated=updated, unchanged=len(rows) - len(written))
