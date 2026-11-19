"""Step 26's "done when": scores stay within 0-100 and inactive components drop out.

Upload -> parse -> score -> rank through the real pipeline and database (fake encoder;
the real-model numbers are checked in tests/unit/matching).
"""

import uuid
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import MatchResult, Resume
from app.models.enums import ParseStatus
from app.repositories.matches import assign_ranks
from app.services.matching import runner
from app.services.matching.scoring_config import DEFAULT_WEIGHTS, SCORING_VERSION
from app.services.storage import FileStore
from tests.fakes import FakeEncoder
from tests.integration.conftest import make_api_app, wire
from tests.integration.factories import make_batch, make_job, make_match, make_resume
from tests.samples import AS_OF, GROUND_TRUTH, SAMPLES, jd, jd_text

pytestmark = pytest.mark.integration

JAVA_JD = jd_text(jd("backend_java"))
# The same JD with no years and no degree: experience and education must drop out.
NO_YEARS_NO_DEGREE = "\n".join(
    line for line in JAVA_JD.split("\n") if "years" not in line and "degree" not in line
)


@pytest.fixture
def client(seeded_session: Session, store: FileStore) -> Iterator[TestClient]:
    app = wire(make_api_app(seeded_session), seeded_session, store)
    with TestClient(app) as c:
        app.state.model_loader.wait(timeout=5)
        yield c


def run_job(client: TestClient, jd_text_: str) -> str:
    job_id: str = client.post("/api/v1/jobs", json={"text": jd_text_}).json()["id"]
    files = [
        ("files", (r["file"].rsplit("/", 1)[-1], (SAMPLES / r["file"]).read_bytes()))
        for r in GROUND_TRUTH["resumes"]
    ]
    response = client.post(f"/api/v1/jobs/{job_id}/resumes", files=files)
    assert response.status_code == 202
    return job_id


def results(session: Session, job_id: str) -> list[MatchResult]:
    session.expire_all()
    return list(
        session.scalars(
            select(MatchResult)
            .where(MatchResult.job_id == uuid.UUID(job_id))
            .order_by(MatchResult.rank)
        )
    )


def test_every_parsed_resume_is_scored_and_ranked(
    client: TestClient, seeded_session: Session
) -> None:
    rows = results(seeded_session, run_job(client, JAVA_JD))

    assert len(rows) == 14  # the 15th file failed to parse: nothing to score
    assert [r.rank for r in rows] == list(range(1, 15))
    for row in rows:
        assert Decimal(0) <= row.overall_score <= Decimal(100)
        parts = (row.skill_score, row.semantic_score, row.experience_score, row.education_score)
        for component in parts:
            assert component is not None and Decimal(0) <= component <= Decimal(1)
        assert (row.scoring_version, row.weights_used, row.is_stale) == (
            SCORING_VERSION,
            DEFAULT_WEIGHTS,
            False,
        )
    scores = [r.overall_score for r in rows]
    assert scores == sorted(scores, reverse=True)


def test_inactive_components_drop_out(client: TestClient, seeded_session: Session) -> None:
    rows = results(seeded_session, run_job(client, NO_YEARS_NO_DEGREE))

    assert rows
    for row in rows:
        assert (row.experience_score, row.education_score) == (None, None)
        weights = row.explanation["details"]["effective_weights"]
        assert weights["experience"] == weights["education"] == 0.0
        assert weights["skills"] == pytest.approx(0.4 / 0.7)
        expected = 100 * (
            weights["skills"] * float(row.skill_score or 0)
            + weights["semantic"] * float(row.semantic_score or 0)
        )
        # Stored components have 3 decimals, the total 2: recomputing drifts by <= 0.055.
        assert float(row.overall_score) == pytest.approx(expected, abs=0.06)


def test_stored_details_feed_the_candidate_view(
    client: TestClient, seeded_session: Session
) -> None:
    rows = results(seeded_session, run_job(client, JAVA_JD))
    row = next(r for r in rows if r.missing_skills)
    skills = {m["skill"] for m in row.matched_skills} | {m["skill"] for m in row.missing_skills}
    assert skills == {
        "Java", "Spring Boot", "PostgreSQL", "REST APIs", "Microservices", "Docker", "Kafka", "AWS",
    }  # fmt: skip
    assert all({"tier", "credit", "evidence"} <= set(m) for m in row.matched_skills)
    assert len(row.requirement_matches) == 14  # 16 minus years and degree
    details: dict[str, Any] = row.explanation["details"]
    expected = {"components", "effective_weights", "semantic", "experience", "education"}
    assert expected <= set(details)


def test_rescoring_is_an_upsert(client: TestClient, seeded_session: Session) -> None:
    job_id = run_job(client, JAVA_JD)
    before = {r.resume_id: (r.overall_score, r.rank) for r in results(seeded_session, job_id)}
    seeded_session.execute(update(MatchResult).values(is_stale=True))  # e.g. a requirement edit

    count = runner.score_job(seeded_session, uuid.UUID(job_id), FakeEncoder(), today=AS_OF)

    after = results(seeded_session, job_id)
    assert count == len(after) == 14  # replaced, never duplicated
    assert {r.resume_id: (r.overall_score, r.rank) for r in after} == before
    assert not any(r.is_stale for r in after)


def test_ties_go_to_required_coverage_then_relevant_experience(seeded_session: Session) -> None:
    job = make_job()
    batch = make_batch(job, total_files=3)
    resumes = [make_resume(batch) for _ in range(3)]
    seeded_session.add_all([job, batch, *resumes])
    seeded_session.flush()
    rows = [
        make_match(job, resumes[0], overall_score=Decimal("70.00"),
                   required_skill_coverage=Decimal("0.600"), relevant_experience_months=60),
        make_match(job, resumes[1], overall_score=Decimal("70.00"),
                   required_skill_coverage=Decimal("0.800"), relevant_experience_months=12),
        make_match(job, resumes[2], overall_score=Decimal("70.00"),
                   required_skill_coverage=Decimal("0.600"), relevant_experience_months=72),
    ]  # fmt: skip
    seeded_session.add_all(rows)
    seeded_session.flush()

    assign_ranks(seeded_session, job.id)

    seeded_session.expire_all()
    assert [r.rank for r in rows] == [3, 1, 2]


def test_a_scoring_failure_keeps_the_parse(
    client: TestClient, seeded_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: object, **kwargs: object) -> None:
        raise RuntimeError("scoring bug")

    monkeypatch.setattr("app.services.pipeline.score_resume", broken)
    job_id = run_job(client, JAVA_JD)

    parsed = seeded_session.scalar(
        select(func.count())
        .where(Resume.parse_status == ParseStatus.PARSED)
        .where(Resume.batch.has(job_id=uuid.UUID(job_id)))
    )
    assert parsed == 14  # parsing stood
    assert results(seeded_session, job_id) == []  # scoring can be rerun later


def test_stored_explanations_add_up_to_the_stored_score(
    client: TestClient, seeded_session: Session
) -> None:
    for row in results(seeded_session, run_job(client, JAVA_JD)):
        explanation = row.explanation
        earned = sum(p["earned"] for p in explanation["breakdown"])
        assert earned == pytest.approx(round(float(row.overall_score), 1))
        assert explanation["verdict"] in {"strong", "good", "partial", "weak"}
        assert explanation["summary"].startswith(explanation["verdict"].capitalize())
        assert all(g["impact"] < 0 for g in explanation["gaps"])
        assert "details" in explanation  # the step-26 details are kept alongside
