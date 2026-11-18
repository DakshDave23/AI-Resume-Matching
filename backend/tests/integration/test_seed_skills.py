"""The taxonomy upsert is idempotent and never duplicates or deletes skills.

Uses made-up skill names so the tests don't depend on what the dev DB has already seeded.
"""

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Skill
from app.repositories.skills import SeedResult, upsert_taxonomy
from app.services.nlp.taxonomy import Taxonomy

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
