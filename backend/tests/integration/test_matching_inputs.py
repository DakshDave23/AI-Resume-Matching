"""The matcher's inputs, read back from what the pipeline stored."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models import JobSkill
from app.models.enums import FileType, RequirementType, SkillAddedBy, SkillCategory
from app.repositories.jobs import save_parsed_job
from app.repositories.resumes import save_parsed_resume
from app.repositories.skills import add_custom_skill, fill_skill_embeddings
from app.services.matching.education import DegreeInput, education_score
from app.services.matching.experience import experience_score
from app.services.matching.inputs import load_candidate, load_job_skills, load_requirements
from app.services.matching.semantic import semantic_score
from app.services.matching.skills import Tier, match_skills, prepare_job
from app.services.nlp.vectors import embed_job, embed_resume
from app.services.parsing.chunker import chunk_resume
from app.services.parsing.jd_parser import parse_job
from app.services.parsing.resume_parser import parse_resume
from tests.fakes import FakeEncoder
from tests.integration.factories import make_batch, make_job, make_resume
from tests.samples import AS_OF, jd, jd_text, resume_text, text_resume

pytestmark = pytest.mark.integration


@pytest.fixture
def stored(seeded_session: Session) -> tuple[Session, uuid.UUID, uuid.UUID]:
    """The Java JD and Candidate A (sample 3), saved as the pipeline saves them."""
    session, encoder = seeded_session, FakeEncoder()
    fill_skill_embeddings(session, encoder)  # a fresh CI database has none yet
    job = make_job(raw_text=jd_text(jd("backend_java")))
    session.add(job)
    session.flush()
    parsed_job = parse_job(job.raw_text)
    save_parsed_job(session, job, parsed_job, embed_job(parsed_job.requirements, encoder))

    batch = make_batch(job)
    resume = make_resume(batch, storage_path=f"{uuid.uuid4()}.pdf", file_type=FileType.PDF)
    session.add_all([batch, resume])
    session.flush()
    text = resume_text(text_resume(3))
    parsed = parse_resume(text, today=AS_OF, region="IN")
    chunks = chunk_resume(parsed.sections, parsed.work)
    vectors = embed_resume(chunks, parsed.work.roles, encoder)
    save_parsed_resume(
        session, resume, text=text, parsed=parsed, chunks=chunks, vectors=vectors, today=AS_OF
    )
    return session, job.id, resume.id


def test_job_skills_load_required_first_with_vectors(
    stored: tuple[Session, uuid.UUID, uuid.UUID],
) -> None:
    session, job_id, _ = stored
    skills = load_job_skills(session, job_id)

    assert [(s.name, s.requirement_type.value, s.weight) for s in skills] == [
        ("Java", "required", 1.0),
        ("Microservices", "required", 1.0),
        ("PostgreSQL", "required", 1.0),
        ("REST APIs", "required", 1.0),
        ("Spring Boot", "required", 1.0),
        ("AWS", "preferred", 0.5),
        ("Docker", "preferred", 0.5),
        ("Kafka", "preferred", 0.5),
    ]
    assert all(s.vector is not None and s.vector.shape == (384,) for s in skills)
    assert {s.name: s.category for s in skills}["Kafka"] == "messaging"


def test_a_candidate_loads_with_terms_years_and_experience_passages(
    stored: tuple[Session, uuid.UUID, uuid.UUID],
) -> None:
    session, _, resume_id = stored
    candidate = load_candidate(session, resume_id)
    skills, passages, text = candidate.skills, candidate.passages, candidate.text

    by_name = {s.name: s for s in skills}
    assert by_name["REST APIs"].terms == ("REST",)  # so the matcher can say "alias"
    assert by_name["Java"].years_used == 4.5  # the Java Developer role, Jun 2022 - Present
    assert by_name["Git"].years_used is None  # listed, never in a dated role
    assert [p.section for p in passages] == ["summary", "experience", "experience"]
    assert passages[1].text.startswith("Java Developer | Contoso Payments")
    assert "Rahul Verma" in text


def test_tiers_from_stored_data(stored: tuple[Session, uuid.UUID, uuid.UUID]) -> None:
    session, job_id, resume_id = stored
    candidate = load_candidate(session, resume_id)
    skills, passages, text = candidate.skills, candidate.passages, candidate.text
    prepared = prepare_job(load_job_skills(session, job_id), FakeEncoder())

    result = match_skills(prepared, skills, passages, resume_text=text)
    tiers = {m.name: m.tier for m in result.matches}

    assert (tiers["Java"], tiers["REST APIs"], tiers["Docker"]) == (
        Tier.EXACT,
        Tier.ALIAS,
        Tier.EXACT,
    )
    assert tiers["AWS"] == Tier.MISSING


def test_a_custom_skill_is_found_in_the_stored_text(
    stored: tuple[Session, uuid.UUID, uuid.UUID],
) -> None:
    session, job_id, resume_id = stored
    custom = add_custom_skill(session, "Deployment Runbooks", SkillCategory.DEVOPS, FakeEncoder())
    session.add(
        JobSkill(
            job_id=job_id,
            skill_id=custom.id,
            requirement_type=RequirementType.PREFERRED,
            weight=Decimal("0.50"),
            added_by=SkillAddedBy.RECRUITER,
        )
    )
    session.flush()
    candidate = load_candidate(session, resume_id)
    skills, passages, text = candidate.skills, candidate.passages, candidate.text
    prepared = prepare_job(load_job_skills(session, job_id), FakeEncoder())

    result = match_skills(prepared, skills, passages, resume_text=text)

    match = next(m for m in result.matches if m.name == "Deployment Runbooks")
    assert match.tier == Tier.EXACT
    assert match.evidence is not None and "deployment runbooks" in match.evidence


def test_semantic_inputs_load_in_jd_order_with_vectors(
    stored: tuple[Session, uuid.UUID, uuid.UUID],
) -> None:
    session, job_id, resume_id = stored
    requirements, job_vector = load_requirements(session, job_id)
    candidate = load_candidate(session, resume_id)

    assert len(requirements) == 16 and job_vector is not None
    assert requirements[0].text.startswith("Design and build scalable backend services")
    assert all(r.requirement_id is not None for r in requirements)
    result = semantic_score(
        requirements, candidate.passages, job_vector=job_vector, resume_vector=candidate.vector
    )
    assert result is not None
    assert len(result.matches) == 14  # 16 minus the years and the degree sentence
    assert 0.0 <= result.score <= 1.0
    assert all(m.evidence for m in result.matches)


def test_roles_load_with_dates_and_vectors(stored: tuple[Session, uuid.UUID, uuid.UUID]) -> None:
    session, _, resume_id = stored
    candidate = load_candidate(session, resume_id)

    assert [(r.title, r.start, r.end, r.is_current) for r in candidate.roles] == [
        ("Java Developer", date(2022, 6, 1), None, True),
        ("Technical Support Engineer", date(2021, 6, 1), date(2022, 5, 1), False),
    ]
    assert all(r.vector is not None and not r.is_internship for r in candidate.roles)
    assert (candidate.total_months, candidate.stated_months) == (66, None)  # from dates
    profile = candidate.roles[0].vector
    assert profile is not None
    result = experience_score(profile, candidate.roles, today=AS_OF, min_years=4)
    assert result.relevant_months >= 54  # the first role compared with itself: relevant


def test_degrees_load_for_the_education_score(
    stored: tuple[Session, uuid.UUID, uuid.UUID],
) -> None:
    session, _, resume_id = stored
    degrees = load_candidate(session, resume_id).degrees

    assert degrees == [DegreeInput("B.Tech", 3, "Computer Science")]
    result = education_score(
        degrees, required_level=3, required_fields=["Computer Science", "Information Technology"]
    )
    assert result.score == 1.0
