"""Database reads and writes for the skills taxonomy."""

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import case, func, literal_column, null, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from sqlalchemy.sql.dml import ReturningInsert

from app.models import Skill
from app.models.enums import SkillCategory
from app.services.nlp.embedder import TextEncoder
from app.services.nlp.taxonomy import Taxonomy, normalize_term


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
    - A skill whose name or category changes loses its embedding, so the next
      `fill_skill_embeddings` recomputes it.
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
    renamed = or_(
        Skill.canonical_name.is_distinct_from(new.canonical_name),
        Skill.category.is_distinct_from(new.category),
    )
    upsert: ReturningInsert[tuple[bool]] = insert_stmt.on_conflict_do_update(
        index_elements=[func.lower(Skill.canonical_name)],
        set_={
            "canonical_name": new.canonical_name,
            "category": new.category,
            "aliases": new.aliases,
            "is_custom": False,
            "embedding": case((renamed, null()), else_=Skill.embedding),
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


def skill_embedding_text(name: str, category: str) -> str:
    """What a skill's vector is computed from: "Kafka (messaging)".

    The category keeps a bare name from drifting to its everyday meaning and pulls
    skills of one family together: measured with all-MiniLM-L6-v2, Kafka/RabbitMQ
    scores 0.59 this way against 0.28 for the names alone, while Kafka/Kubernetes
    stays at 0.22. (The design doc says "name plus a short description"; the
    taxonomy has no descriptions, and per-category descriptions lifted unrelated
    pairs as much as related ones.)
    """
    return f"{name} ({category})"


def fill_skill_embeddings(
    session: Session, encoder: TextEncoder, *, everything: bool = False
) -> int:
    """Embed skills that have no vector yet (or all of them, after a model change).

    Returns how many skills were embedded. All texts go to the model in one batched call.
    """
    query = select(Skill).order_by(Skill.id)
    if not everything:
        query = query.where(Skill.embedding.is_(None))
    skills = session.scalars(query).all()
    vectors = encoder.encode([skill_embedding_text(s.canonical_name, s.category) for s in skills])
    for skill, vector in zip(skills, vectors, strict=True):
        skill.embedding = vector.tolist()
    session.flush()
    return len(skills)


def count_skills_without_embedding(session: Session) -> int:
    return session.scalar(select(func.count()).where(Skill.embedding.is_(None))) or 0


class SkillsNotSeededError(RuntimeError):
    """The parser found skills the skills table doesn't have: the seed script hasn't run."""

    def __init__(self, missing: list[str]) -> None:
        super().__init__(
            f"{len(missing)} skill(s) missing from the skills table ({', '.join(missing[:5])}"
            f"{', ...' if len(missing) > 5 else ''}); run scripts/seed_skills.py"
        )
        self.missing = missing


def skill_ids(session: Session, names: Iterable[str]) -> dict[str, int]:
    """Canonical name -> skills.id, for names the extractor produced from the taxonomy file."""
    wanted = set(names)
    if not wanted:
        return {}
    rows = session.execute(
        select(Skill.canonical_name, Skill.id).where(Skill.canonical_name.in_(wanted))
    ).all()
    found = {name: skill_id for name, skill_id in rows}
    if missing := sorted(wanted - found.keys()):
        raise SkillsNotSeededError(missing)
    return found


def find_skill(session: Session, name: str) -> Skill | None:
    """A skill by canonical name or alias, ignoring case: "k8s" finds Kubernetes."""
    key = normalize_term(name)
    by_name = session.scalars(select(Skill).where(func.lower(Skill.canonical_name) == key)).first()
    if by_name is not None:
        return by_name
    # `aliases @> ARRAY[key]` can use the GIN index on aliases.
    return session.scalars(
        select(Skill).where(Skill.aliases.contains([key])).order_by(Skill.id)
    ).first()


def add_custom_skill(
    session: Session, name: str, category: SkillCategory, encoder: TextEncoder
) -> Skill:
    """A recruiter's skill that the taxonomy lacks ("Add to taxonomy"), with its vector.

    Safe if two requests add the same name at once: the second finds the first's row.
    """
    vector = encoder.encode([skill_embedding_text(name, category.value)])[0]
    statement = (
        insert(Skill)
        .values(
            canonical_name=name,
            category=category.value,
            aliases=[],
            is_custom=True,
            embedding=vector.tolist(),
        )
        .on_conflict_do_nothing(index_elements=[func.lower(Skill.canonical_name)])
    )
    session.execute(statement)
    skill = find_skill(session, name)
    if skill is None:  # pragma: no cover - the row was just inserted or already there
        raise RuntimeError(f"custom skill {name!r} was not saved")
    return skill
