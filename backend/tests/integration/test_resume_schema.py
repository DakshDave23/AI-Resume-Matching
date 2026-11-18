"""The database enforces the resume, batch, candidate and match invariants (design doc §4)."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Candidate,
    Education,
    Job,
    MatchResult,
    Resume,
    ResumeChunk,
    ResumeSkill,
    Skill,
    UploadBatch,
    WorkExperience,
)
from app.models.enums import BatchStatus, ParseStatus, SkillSource
from tests.integration.factories import VECTOR, make_batch, make_job, make_match, make_resume

pytestmark = pytest.mark.integration

NOW = datetime(2026, 11, 18, tzinfo=UTC)


def test_parsed_resume_round_trips_with_all_children(db_session: Session) -> None:
    java = Skill(canonical_name="Zz Java", category="language")
    resume = make_resume(
        make_batch(),
        candidate=Candidate(full_name="Asha Rao", email="asha@example.com", phone="+919876543210"),
        parse_status=ParseStatus.PARSED,
        parsed_at=NOW,
        parse_confidence=Decimal("0.83"),
        total_experience_months=66,
        highest_degree_level=3,
        sections={"experience": "Senior Engineer at Acme Fintech ..."},
        embedding=VECTOR,
    )
    resume.skills = [
        ResumeSkill(
            skill=java,
            sources=[SkillSource.SKILLS_SECTION, SkillSource.EXPERIENCE],
            mention_count=4,
            years_used=Decimal("5.5"),
            evidence="Built payment services in Java 17",
        )
    ]
    resume.work_experiences = [
        WorkExperience(
            job_title="Senior Engineer",
            company="Acme Fintech",
            start_date=date(2021, 1, 1),
            is_current=True,
            duration_months=70,
        )
    ]
    resume.educations = [Education(degree_raw="B.Tech", degree_level=3, graduation_year=2019)]
    resume.chunks = [
        ResumeChunk(section="experience", chunk_index=0, text="Built…", embedding=VECTOR)
    ]
    db_session.add(resume)
    db_session.flush()
    db_session.expunge_all()

    loaded = db_session.scalars(
        select(Resume)
        .where(Resume.id == resume.id)
        .options(
            selectinload(Resume.candidate),
            selectinload(Resume.skills).selectinload(ResumeSkill.skill),
            selectinload(Resume.work_experiences),
            selectinload(Resume.educations),
            selectinload(Resume.chunks),
        )
    ).one()

    assert loaded.candidate is not None
    assert loaded.candidate.email == "asha@example.com"
    # An array of a Postgres ENUM type comes back as Python enum members.
    assert loaded.skills[0].sources == [SkillSource.SKILLS_SECTION, SkillSource.EXPERIENCE]
    assert loaded.skills[0].skill.canonical_name == "Zz Java"
    assert loaded.work_experiences[0].is_current is True
    assert loaded.educations[0].degree_level == 3
    assert loaded.chunks[0].embedding == pytest.approx(VECTOR)


# --- upload_batches ---------------------------------------------------------


@pytest.mark.parametrize(
    ("fields", "constraint"),
    [
        ({"total_files": 0}, "total_files_positive"),
        ({"total_files": 2, "processed_files": 2, "failed_files": 1}, "counts_within_total"),
        ({"completed_at": NOW}, "completed_at_matches_status"),
        ({"status": BatchStatus.COMPLETED}, "completed_at_matches_status"),
        (
            {"status": BatchStatus.COMPLETED, "completed_at": NOW, "total_files": 3},
            "finished_means_all_counted",
        ),
        (
            {"status": BatchStatus.COMPLETED, "completed_at": NOW, "failed_files": 1},
            "completed_has_no_failures",
        ),
        (
            {
                "status": BatchStatus.COMPLETED_WITH_ERRORS,
                "completed_at": NOW,
                "processed_files": 1,
            },
            "completed_with_errors_has_failures",
        ),
    ],
    ids=[
        "no-files",
        "counts-exceed-total",
        "processing-but-has-completed-at",
        "completed-without-completed-at",
        "completed-with-files-uncounted",
        "completed-but-has-failures",
        "with-errors-but-no-failures",
    ],
)
def test_batch_status_can_never_contradict_its_counts(
    db_session: Session, fields: dict[str, Any], constraint: str
) -> None:
    db_session.add(make_batch(**fields))

    with pytest.raises(IntegrityError, match=f"ck_upload_batches_{constraint}"):
        db_session.flush()


def test_a_finished_batch_with_one_failure_is_valid(db_session: Session) -> None:
    batch = make_batch(
        total_files=15,
        processed_files=14,
        failed_files=1,
        status=BatchStatus.COMPLETED_WITH_ERRORS,
        completed_at=NOW,
    )
    db_session.add(batch)
    db_session.flush()  # no error


# --- resumes ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("fields", "constraint"),
    [
        ({"parse_status": ParseStatus.FAILED}, "error_iff_failed"),
        (
            {"parse_status": ParseStatus.PARSED, "parsed_at": NOW, "parse_error": "oops"},
            "error_iff_failed",
        ),
        ({"parse_status": ParseStatus.PARSED}, "parsed_has_timestamp"),
        ({"file_size_bytes": 5 * 1024 * 1024 + 1}, "file_size_range"),
        ({"file_sha256": "NOT-A-HASH"}, "sha256_hex"),
        ({"parse_confidence": Decimal("1.5")}, "confidence_range"),
    ],
    ids=[
        "failed-without-reason",
        "parsed-with-error",
        "parsed-without-timestamp",
        "file-over-5mb",
        "bad-sha256",
        "confidence-above-1",
    ],
)
def test_resume_rejects_invalid_states(
    db_session: Session, fields: dict[str, Any], constraint: str
) -> None:
    db_session.add(make_resume(make_batch(), **fields))

    with pytest.raises(IntegrityError, match=f"ck_resumes_{constraint}"):
        db_session.flush()


def test_a_failed_resume_with_a_reason_is_valid(db_session: Session) -> None:
    db_session.add(
        make_resume(
            make_batch(),
            parse_status=ParseStatus.FAILED,
            parse_error="Looks like a scanned image; OCR is not enabled",
        )
    )
    db_session.flush()  # no error


def test_same_file_twice_in_one_batch_is_rejected(db_session: Session) -> None:
    batch = make_batch(total_files=2)
    first = make_resume(batch)
    db_session.add_all([first, make_resume(batch, file_sha256=first.file_sha256)])

    with pytest.raises(IntegrityError, match="uq_resumes_batch_id_file_sha256"):
        db_session.flush()


def test_same_file_in_two_batches_is_allowed(db_session: Session) -> None:
    first = make_resume(make_batch())
    db_session.add_all([first, make_resume(make_batch(), file_sha256=first.file_sha256)])
    db_session.flush()  # no error


# --- candidates -------------------------------------------------------------


def test_candidate_email_is_unique_ignoring_case_but_may_be_missing(db_session: Session) -> None:
    db_session.add_all([Candidate(full_name="No Email 1"), Candidate(full_name="No Email 2")])
    db_session.add(Candidate(email="Asha@Example.com"))
    db_session.flush()  # several null emails are fine

    db_session.add(Candidate(email="asha@example.com"))
    with pytest.raises(IntegrityError, match="uq_candidates_email_lower"):
        db_session.flush()


@pytest.mark.parametrize("phone", ["9876543210", "+0123456789", "+91 98765 43210"])
def test_candidate_phone_must_be_e164(db_session: Session, phone: str) -> None:
    db_session.add(Candidate(phone=phone))

    with pytest.raises(IntegrityError, match="ck_candidates_phone_e164"):
        db_session.flush()


def test_a_candidate_with_resumes_cannot_be_deleted(db_session: Session) -> None:
    candidate = Candidate(email="asha@example.com")
    db_session.add(make_resume(make_batch(), candidate=candidate))
    db_session.flush()

    with pytest.raises(IntegrityError, match="fk_resumes_candidate_id_candidates"):
        db_session.execute(delete(Candidate).where(Candidate.id == candidate.id))


# --- children of resumes ----------------------------------------------------


@pytest.mark.parametrize(
    ("fields", "constraint"),
    [
        ({"start_date": date(2022, 1, 1), "end_date": date(2021, 1, 1)}, "end_after_start"),
        ({"is_current": True, "end_date": date(2024, 1, 1)}, "current_has_no_end"),
    ],
    ids=["ends-before-it-starts", "current-role-with-end-date"],
)
def test_work_experience_dates_must_make_sense(
    db_session: Session, fields: dict[str, Any], constraint: str
) -> None:
    resume = make_resume(make_batch())
    resume.work_experiences = [WorkExperience(**fields)]
    db_session.add(resume)

    with pytest.raises(IntegrityError, match=f"ck_work_experiences_{constraint}"):
        db_session.flush()


def test_a_resume_skill_needs_at_least_one_source(db_session: Session) -> None:
    resume = make_resume(make_batch())
    resume.skills = [
        ResumeSkill(
            skill=Skill(canonical_name="Zz Go", category="language"), sources=[], mention_count=1
        )
    ]
    db_session.add(resume)

    with pytest.raises(IntegrityError, match="ck_resume_skills_has_source"):
        db_session.flush()


def test_chunk_section_must_be_known(db_session: Session) -> None:
    resume = make_resume(make_batch())
    resume.chunks = [ResumeChunk(section="hobbies", chunk_index=0, text="Chess", embedding=VECTOR)]
    db_session.add(resume)

    with pytest.raises(IntegrityError, match="ck_resume_chunks_section_valid"):
        db_session.flush()


# --- match_results ----------------------------------------------------------


def test_one_match_result_per_job_and_resume(db_session: Session) -> None:
    job = make_job()
    resume = make_resume(make_batch(job))
    db_session.add_all([make_match(job, resume), make_match(job, resume)])

    with pytest.raises(IntegrityError, match="uq_match_results_job_id_resume_id"):
        db_session.flush()


@pytest.mark.parametrize(
    ("fields", "constraint"),
    [
        ({"overall_score": Decimal("100.01")}, "overall_score_range"),
        ({"semantic_score": Decimal("1.2")}, "component_scores_range"),
        ({"rank": 0}, "rank_positive"),
    ],
    ids=["score-above-100", "component-above-1", "rank-zero"],
)
def test_match_scores_stay_in_range(
    db_session: Session, fields: dict[str, Any], constraint: str
) -> None:
    job = make_job()
    db_session.add(make_match(job, make_resume(make_batch(job)), **fields))

    with pytest.raises(IntegrityError, match=f"ck_match_results_{constraint}"):
        db_session.flush()


def test_inactive_components_may_be_null(db_session: Session) -> None:
    job = make_job()
    match = make_match(
        job, make_resume(make_batch(job)), experience_score=None, education_score=None
    )
    db_session.add(match)
    db_session.flush()
    db_session.refresh(match)

    assert match.experience_score is None
    assert match.matched_skills == []  # JSONB defaults from the database
    assert match.is_stale is False


# --- cascades ---------------------------------------------------------------


def test_deleting_a_job_removes_everything_below_it_but_keeps_shared_rows(
    db_session: Session,
) -> None:
    job = make_job()
    candidate = Candidate(email="asha@example.com")
    skill = Skill(canonical_name="Zz Kafka", category="messaging")
    resume = make_resume(make_batch(job), candidate=candidate)
    resume.skills = [ResumeSkill(skill=skill, sources=[SkillSource.EXPERIENCE], mention_count=1)]
    resume.work_experiences = [WorkExperience(job_title="Engineer")]
    resume.educations = [Education(degree_level=3)]
    resume.chunks = [ResumeChunk(section="summary", chunk_index=0, text="Hi", embedding=VECTOR)]
    db_session.add_all([resume, make_match(job, resume)])
    db_session.flush()

    # Only the job is deleted; ON DELETE CASCADE must do the rest.
    db_session.execute(delete(Job).where(Job.id == job.id))

    def count(model: type[Any], *where: Any) -> int | None:
        return db_session.scalar(select(func.count()).select_from(model).where(*where))

    assert count(UploadBatch, UploadBatch.job_id == job.id) == 0
    assert count(Resume, Resume.id == resume.id) == 0
    for child in (ResumeSkill, WorkExperience, Education, ResumeChunk):
        assert count(child, child.resume_id == resume.id) == 0
    assert count(MatchResult, MatchResult.job_id == job.id) == 0
    # Shared rows survive.
    assert count(Candidate, Candidate.id == candidate.id) == 1
    assert count(Skill, Skill.id == skill.id) == 1
