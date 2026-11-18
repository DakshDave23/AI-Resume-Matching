"""The database itself enforces the job/skill invariants from design doc §4."""

from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError, InvalidRequestError
from sqlalchemy.orm import Session, selectinload

from app.models import Job, JobRequirement, JobSkill, Skill
from app.models.enums import JobStatus, RequirementType, SkillAddedBy
from app.services.matching.scoring_config import DEFAULT_WEIGHTS
from tests.integration.factories import VECTOR, make_job, make_requirement

pytestmark = pytest.mark.integration


def test_job_defaults_come_from_the_database(db_session: Session) -> None:
    job = make_job()
    db_session.add(job)
    db_session.flush()
    db_session.refresh(job)

    assert job.id is not None
    assert job.status is JobStatus.DRAFT
    assert job.scoring_weights == DEFAULT_WEIGHTS
    assert job.required_fields_of_study == []
    assert job.accepts_equivalent_experience is False
    assert job.created_at is not None


def test_job_round_trips_with_requirements_skills_and_vectors(db_session: Session) -> None:
    java = Skill(canonical_name="Java", category="language", aliases=["java8", "core java"])
    job = make_job(embedding=VECTOR, min_experience_years=Decimal("4"), required_degree_level=3)
    job.requirements = [make_requirement(0), make_requirement(1)]
    job.skills = [JobSkill(skill=java, requirement_type=RequirementType.REQUIRED)]
    db_session.add(job)
    db_session.flush()
    db_session.expunge_all()  # force a real reload from the database

    loaded = db_session.scalars(
        select(Job)
        .where(Job.id == job.id)
        .options(
            selectinload(Job.requirements),
            selectinload(Job.skills).selectinload(JobSkill.skill),
        )
    ).one()

    assert loaded.embedding == pytest.approx(VECTOR)
    assert [r.position for r in loaded.requirements] == [0, 1]
    assert loaded.requirements[0].embedding == pytest.approx(VECTOR)
    job_skill = loaded.skills[0]
    assert job_skill.skill.aliases == ["java8", "core java"]
    assert job_skill.weight == Decimal("1.00")
    assert job_skill.added_by == SkillAddedBy.PARSER


def test_relationships_must_be_loaded_explicitly(db_session: Session) -> None:
    job = make_job()
    db_session.add(job)
    db_session.flush()
    db_session.expunge_all()

    loaded = db_session.get_one(Job, job.id)

    # lazy="raise" turns a hidden N+1 query into an immediate error.
    with pytest.raises(InvalidRequestError):
        _ = loaded.requirements


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        (
            {"min_experience_years": Decimal("5"), "max_experience_years": Decimal("3")},
            "ck_jobs_max_experience_gte_min",
        ),
        ({"min_experience_years": Decimal("-1")}, "ck_jobs_min_experience_non_negative"),
        ({"required_degree_level": 6}, "ck_jobs_degree_level_range"),
        ({"title": "   "}, "ck_jobs_title_not_blank"),
    ],
    ids=["max-below-min", "negative-years", "degree-level-6", "blank-title"],
)
def test_job_rejects_invalid_values(
    db_session: Session, overrides: dict[str, Any], constraint: str
) -> None:
    db_session.add(make_job(**overrides))

    with pytest.raises(IntegrityError, match=constraint):
        db_session.flush()


def test_skill_names_are_unique_ignoring_case(db_session: Session) -> None:
    db_session.add(Skill(canonical_name="PostgreSQL", category="database"))
    db_session.flush()
    db_session.add(Skill(canonical_name="postgresql", category="database"))

    with pytest.raises(IntegrityError, match="uq_skills_canonical_name_lower"):
        db_session.flush()


@pytest.mark.parametrize("weight", [Decimal("0"), Decimal("1.5")])
def test_job_skill_weight_must_be_in_range(db_session: Session, weight: Decimal) -> None:
    job = make_job()
    job.skills = [
        JobSkill(
            skill=Skill(canonical_name="Kafka", category="tool"),
            requirement_type=RequirementType.PREFERRED,
            weight=weight,
        )
    ]
    db_session.add(job)

    with pytest.raises(IntegrityError, match="ck_job_skills_weight_range"):
        db_session.flush()


def test_requirement_positions_are_unique_per_job(db_session: Session) -> None:
    job = make_job()
    job.requirements = [make_requirement(0), make_requirement(0)]
    db_session.add(job)

    with pytest.raises(IntegrityError, match="uq_job_requirements_job_id_position"):
        db_session.flush()


def test_deleting_a_job_cascades_but_keeps_shared_skills(db_session: Session) -> None:
    skill = Skill(canonical_name="Spring Boot", category="framework")
    job = make_job()
    job.requirements = [make_requirement(0)]
    job.skills = [JobSkill(skill=skill, requirement_type=RequirementType.REQUIRED)]
    db_session.add(job)
    db_session.flush()

    db_session.execute(delete(Job).where(Job.id == job.id))

    count = select(func.count())
    assert db_session.scalar(count.where(JobRequirement.job_id == job.id)) == 0
    assert db_session.scalar(count.where(JobSkill.job_id == job.id)) == 0
    assert db_session.scalar(count.where(Skill.id == skill.id)) == 1


def test_a_skill_in_use_cannot_be_deleted(db_session: Session) -> None:
    skill = Skill(canonical_name="Docker", category="devops")
    job = make_job()
    job.skills = [JobSkill(skill=skill, requirement_type=RequirementType.PREFERRED)]
    db_session.add(job)
    db_session.flush()

    with pytest.raises(IntegrityError, match="fk_job_skills_skill_id_skills"):
        db_session.execute(delete(Skill).where(Skill.id == skill.id))
