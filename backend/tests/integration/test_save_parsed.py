"""Step 18's "done when": every parsed resume has chunks with vectors.

All 15 samples and the Java JD go through extract -> parse -> chunk -> embed -> save,
inside a transaction that is rolled back. The fake encoder stands in for the model:
these tests are about what gets stored, not about what the vectors mean.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import (
    Candidate,
    Education,
    Job,
    JobRequirement,
    JobSkill,
    Resume,
    ResumeChunk,
    ResumeSkill,
    UploadBatch,
    WorkExperience,
)
from app.models.enums import FileType, JobStatus, ParseStatus, RequirementType
from app.repositories.jobs import save_parsed_job
from app.repositories.resumes import mark_failed, save_parsed_resume
from app.repositories.skills import SkillsNotSeededError, skill_ids
from app.services.extraction import ExtractionError
from app.services.nlp.vectors import embed_job, embed_resume
from app.services.parsing.chunker import chunk_resume
from app.services.parsing.jd_parser import parse_job
from app.services.parsing.resume_parser import parse_resume
from tests.fakes import FakeEncoder
from tests.integration.factories import make_batch, make_job, make_resume
from tests.samples import AS_OF, GROUND_TRUTH, Sample, jd, jd_text, resume_text, text_resume

pytestmark = pytest.mark.integration


@pytest.fixture
def seeded(seeded_session: Session) -> Session:
    return seeded_session


def save_job(session: Session, encoder: FakeEncoder) -> Job:
    job = make_job(title="Senior Backend Java Developer", raw_text=jd_text(jd("backend_java")))
    session.add(job)
    session.flush()
    parsed = parse_job(job.raw_text)
    save_parsed_job(session, job, parsed, embed_job(parsed.requirements, encoder))
    return job


def new_resume(session: Session, batch: UploadBatch, sample: Sample) -> Resume:
    resume = make_resume(
        batch,
        original_filename=sample["file"].rsplit("/", 1)[-1],
        file_type=FileType(sample["format"]),
        storage_path=f"{uuid.uuid4()}.{sample['format']}",
    )
    session.add(resume)
    session.flush()
    return resume


def save_sample(session: Session, resume: Resume, sample: Sample, encoder: FakeEncoder) -> None:
    """What the upload pipeline will do for one file."""
    try:
        text_ = resume_text(sample)
    except ExtractionError as exc:
        mark_failed(resume, exc.message)
        session.flush()
        return
    parsed = parse_resume(text_, today=AS_OF, region="IN")
    chunks = chunk_resume(parsed.sections, parsed.work)
    vectors = embed_resume(chunks, parsed.work.roles, encoder)
    save_parsed_resume(
        session, resume, text=text_, parsed=parsed, chunks=chunks, vectors=vectors, today=AS_OF
    )


def count(session: Session, model: type, **where: object) -> int:
    query = select(func.count()).select_from(model).filter_by(**where)
    return session.scalar(query) or 0


def test_every_parsed_sample_has_chunks_with_vectors(seeded: Session) -> None:
    session, encoder = seeded, FakeEncoder()
    job = save_job(session, encoder)
    batch = make_batch(job, total_files=len(GROUND_TRUTH["resumes"]))
    session.add(batch)
    session.flush()
    for sample in GROUND_TRUTH["resumes"]:
        save_sample(session, new_resume(session, batch, sample), sample, encoder)

    resumes = session.scalars(select(Resume).where(Resume.batch_id == batch.id)).all()
    parsed = [r for r in resumes if r.parse_status == ParseStatus.PARSED]
    failed = [r for r in resumes if r.parse_status == ParseStatus.FAILED]
    assert (len(parsed), len(failed)) == (14, 1)
    assert failed[0].original_filename == "15_scanned_pdf.pdf"
    assert failed[0].parse_error

    stats = session.execute(
        text("""
            SELECT r.id, count(c.id) AS chunks, count(c.embedding) AS embedded,
                   min(vector_dims(c.embedding)) AS dims, r.embedding IS NOT NULL AS has_doc
            FROM resumes r LEFT JOIN resume_chunks c ON c.resume_id = r.id
            WHERE r.batch_id = :batch AND r.parse_status = 'parsed'
            GROUP BY r.id
        """),
        {"batch": batch.id},
    ).all()
    assert len(stats) == 14
    for row in stats:
        assert row.chunks >= 1 and row.embedded == row.chunks, row
        assert row.dims == 384 and row.has_doc, row
    # Every role is embedded too (for role relevance, §6.4).
    roles = session.execute(
        select(func.count(), func.count(WorkExperience.embedding))
        .join(Resume)
        .where(Resume.batch_id == batch.id)
    ).one()
    assert roles[0] == roles[1] == 28


def test_the_java_jd_is_stored_with_embedded_requirements(seeded: Session) -> None:
    job = save_job(seeded, FakeEncoder())

    assert job.status == JobStatus.PARSED
    assert job.company == "Northwind Payments (synthetic)"
    assert job.min_experience_years == Decimal("4.0")
    assert (job.required_degree_level, job.required_fields_of_study) == (
        3,
        ["Computer Science", "Information Technology"],
    )
    assert job.embedding is not None
    assert count(seeded, JobRequirement, job_id=job.id) == 16
    skills = seeded.execute(
        select(JobSkill.requirement_type, JobSkill.weight).where(JobSkill.job_id == job.id)
    ).all()
    assert (
        sorted(skills)
        == [(RequirementType.PREFERRED, Decimal("0.50"))] * 3
        + [(RequirementType.REQUIRED, Decimal("1.00"))] * 5
    )


def test_a_resume_is_stored_completely(seeded: Session) -> None:
    session = seeded
    batch = make_batch(make_job())
    session.add(batch)
    sample = text_resume(1)
    resume = new_resume(session, batch, sample)
    save_sample(session, resume, sample, FakeEncoder())

    candidate = session.get(Candidate, resume.candidate_id)
    assert candidate is not None
    assert (candidate.full_name, candidate.email) == (sample["name"], sample["email"])
    assert resume.total_experience_months == 113
    assert resume.highest_degree_level == 3
    assert resume.current_title == "Senior Software Engineer"
    assert resume.parse_confidence == Decimal("1.00")
    assert resume.sections is not None and "experience" in resume.sections
    assert count(session, ResumeSkill, resume_id=resume.id) == len(sample["skills"])
    assert count(session, Education, resume_id=resume.id) == 1
    java_years = session.scalar(
        select(ResumeSkill.years_used).where(
            ResumeSkill.resume_id == resume.id,
            ResumeSkill.skill_id == skill_ids(session, ["Java"])["Java"],
        )
    )
    assert resume.parsed_json is not None
    assert resume.parsed_json["skill_months"]["Java"] == 45  # only the 2017-2021 role says Java
    assert java_years == Decimal("3.8")  # the table stores years
    roles = session.scalars(
        select(WorkExperience).where(WorkExperience.resume_id == resume.id)
    ).all()
    assert [(r.start_date.isoformat() if r.start_date else None, r.is_current) for r in roles] == [
        ("2021-04-01", True),
        ("2017-07-01", False),
    ]


def test_saving_again_replaces_the_previous_parse(seeded: Session) -> None:
    session = seeded
    batch = make_batch(make_job())
    session.add(batch)
    sample = text_resume(3)
    resume = new_resume(session, batch, sample)
    save_sample(session, resume, sample, FakeEncoder())
    before = count(session, ResumeChunk, resume_id=resume.id)

    save_sample(session, resume, sample, FakeEncoder())

    assert count(session, ResumeChunk, resume_id=resume.id) == before
    assert count(session, WorkExperience, resume_id=resume.id) == 2


def test_two_resumes_of_one_person_share_a_candidate(seeded: Session) -> None:
    session = seeded
    batch = make_batch(make_job(), total_files=2)
    session.add(batch)
    sample = text_resume(4)
    first = new_resume(session, batch, sample)
    save_sample(session, first, sample, FakeEncoder())
    second = make_resume(batch, storage_path=f"{uuid.uuid4()}.docx", file_type=FileType.DOCX)
    session.add(second)
    session.flush()

    save_sample(session, second, sample, FakeEncoder())

    assert second.candidate_id == first.candidate_id
    assert count(session, Candidate, email=sample["email"]) == 1


def test_an_unseeded_skill_fails_loudly(seeded: Session) -> None:
    with pytest.raises(SkillsNotSeededError, match=r"Zz Nope.*seed_skills"):
        skill_ids(seeded, ["Java", "Zz Nope"])
