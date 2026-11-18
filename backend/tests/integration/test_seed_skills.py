"""The taxonomy upsert is idempotent and never duplicates or deletes skills.

Uses made-up skill names so the tests don't depend on what the dev DB has already seeded.
"""

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Skill
from app.repositories.skills import (
    SeedResult,
    fill_skill_embeddings,
    skill_embedding_text,
    upsert_taxonomy,
)
from app.services.nlp.taxonomy import Taxonomy
from tests.fakes import FakeEncoder

pytestmark = pytest.mark.integration


def taxonomy(*skills: dict[str, Any]) -> Taxonomy:
    return Taxonomy.model_validate({"version": "test", "skills": list(skills)})


ALPHA = {"name": "Zz Alpha", "category": "tool", "aliases": ["zz-a"]}
BETA = {"name": "Zz Beta", "category": "tool", "aliases": []}


def get_skill(session: Session, name: str) -> Skill:
    session.expire_all()
    return session.scalars(select(Skill).where(Skill.canonical_name.ilike(name))).one()


def test_first_run_inserts_and_second_run_changes_nothing(db_session: Session) -> None:
    assert upsert_taxonomy(db_session, taxonomy(ALPHA, BETA)) == SeedResult(2, 0, 0)
    assert upsert_taxonomy(db_session, taxonomy(ALPHA, BETA)) == SeedResult(0, 0, 2)


def test_changed_entries_are_updated_in_place(db_session: Session) -> None:
    upsert_taxonomy(db_session, taxonomy(ALPHA, BETA))
    original_id = get_skill(db_session, "Zz Alpha").id

    changed = ALPHA | {"category": "devops", "aliases": ["zz-a", "zz-alpha"]}
    result = upsert_taxonomy(db_session, taxonomy(changed, BETA))

    assert result == SeedResult(inserted=0, updated=1, unchanged=1)
    skill = get_skill(db_session, "Zz Alpha")
    assert skill.id == original_id  # same row, so job/resume links stay valid
    assert skill.category == "devops"
    assert skill.aliases == ["zz-a", "zz-alpha"]


def test_a_custom_skill_with_the_same_name_is_adopted_not_duplicated(db_session: Session) -> None:
    db_session.add(Skill(canonical_name="zz alpha", category="tool", is_custom=True))
    db_session.flush()

    result = upsert_taxonomy(db_session, taxonomy(ALPHA))

    assert result == SeedResult(inserted=0, updated=1, unchanged=0)
    skill = get_skill(db_session, "Zz Alpha")
    assert skill.canonical_name == "Zz Alpha"  # the taxonomy's spelling wins
    assert skill.is_custom is False


def test_skills_missing_from_the_file_are_kept(db_session: Session) -> None:
    upsert_taxonomy(db_session, taxonomy(ALPHA, BETA))

    upsert_taxonomy(db_session, taxonomy(ALPHA))

    assert get_skill(db_session, "Zz Beta").canonical_name == "Zz Beta"


def test_the_database_rejects_an_unknown_category(db_session: Session) -> None:
    db_session.add(Skill(canonical_name="Zz Gamma", category="frameworks"))

    with pytest.raises(IntegrityError, match="ck_skills_category_valid"):
        db_session.flush()


# --- Embeddings ---------------------------------------------------------------------


def test_skill_vectors_come_from_name_and_category() -> None:
    assert skill_embedding_text("Kafka", "messaging") == "Kafka (messaging)"


def test_missing_vectors_are_filled_and_kept_on_the_next_run(db_session: Session) -> None:
    upsert_taxonomy(db_session, taxonomy(ALPHA, BETA))
    encoder = FakeEncoder()

    fill_skill_embeddings(db_session, encoder)
    alpha = get_skill(db_session, "Zz Alpha")
    assert alpha.embedding is not None
    assert len(alpha.embedding) == 384
    assert "Zz Alpha (tool)" in encoder.calls[0]
    assert len(encoder.calls) == 1  # one batched call, not one per skill

    fill_skill_embeddings(db_session, encoder)  # nothing is missing now
    assert encoder.calls[-1] == []


def test_a_renamed_or_recategorised_skill_is_embedded_again(db_session: Session) -> None:
    upsert_taxonomy(db_session, taxonomy(ALPHA, BETA))
    fill_skill_embeddings(db_session, FakeEncoder())

    upsert_taxonomy(db_session, taxonomy(ALPHA | {"category": "devops"}, BETA | {"aliases": ["b"]}))

    assert get_skill(db_session, "Zz Alpha").embedding is None  # category changed
    assert get_skill(db_session, "Zz Beta").embedding is not None  # only an alias changed
    encoder = FakeEncoder()
    fill_skill_embeddings(db_session, encoder)
    assert "Zz Alpha (devops)" in encoder.calls[0]
    assert "Zz Beta (tool)" not in encoder.calls[0]


def test_everything_reembeds_all_skills(db_session: Session) -> None:
    upsert_taxonomy(db_session, taxonomy(ALPHA, BETA))
    fill_skill_embeddings(db_session, FakeEncoder())

    encoder = FakeEncoder()
    count = fill_skill_embeddings(db_session, encoder, everything=True)

    assert count == len(encoder.calls[0]) >= 2
    assert {"Zz Alpha (tool)", "Zz Beta (tool)"} <= set(encoder.calls[0])
