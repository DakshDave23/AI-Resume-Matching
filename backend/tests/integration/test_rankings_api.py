"""Step 28's "done when": rankings are returned in score order.

Also scoring runs, weights, candidate detail and the CSV export, through the real API
and database (fake encoder; rolled back after each test).
"""

import csv
import io
import threading
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session

from app.models import Candidate, Resume
from app.services.nlp.embedder import TextEncoder
from app.services.nlp.loader import ModelLoader
from app.services.storage import FileStore
from tests.fakes import FakeEncoder
from tests.integration.conftest import make_api_app, wire
from tests.samples import GROUND_TRUTH, SAMPLES, jd, jd_text

pytestmark = pytest.mark.integration


@pytest.fixture
def client(seeded_session: Session, store: FileStore) -> Iterator[TestClient]:
    app = wire(make_api_app(seeded_session), seeded_session, store)
    with TestClient(app) as c:
        app.state.model_loader.wait(timeout=5)
        yield c


@pytest.fixture
def job_id(client: TestClient) -> str:
    """The Java JD with all 15 samples uploaded, parsed and scored."""
    job: str = client.post("/api/v1/jobs", json={"text": jd_text(jd("backend_java"))}).json()["id"]
    files = [
        ("files", (r["file"].rsplit("/", 1)[-1], (SAMPLES / r["file"]).read_bytes()))
        for r in GROUND_TRUTH["resumes"]
    ]
    assert client.post(f"/api/v1/jobs/{job}/resumes", files=files).status_code == 202
    return job


def rankings(client: TestClient, job: str, **params: Any) -> dict[str, Any]:
    response = client.get(f"/api/v1/jobs/{job}/rankings", params=params)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


# --- Rankings ----------------------------------------------------------------------------


def test_rankings_come_back_in_score_order(client: TestClient, job_id: str) -> None:
    body = rankings(client, job_id)

    rows = body["rows"]
    assert body["total"] == len(rows) == 14  # the scanned PDF failed: not ranked
    assert [r["rank"] for r in rows] == list(range(1, 15))
    scores = [r["match_percent"] for r in rows]
    assert scores == sorted(scores, reverse=True)
    top = rows[0]
    assert set(top) >= {"name", "current_title", "total_years", "relevant_years", "verdict"}
    assert len(top["top_matched_skills"]) <= 5
    assert all(r["matched_skill_count"] >= len(r["top_matched_skills"]) for r in rows)
    assert all(0 < r["parse_confidence"] <= 1 for r in rows)
    assert all(r["needs_review"] is (r["parse_confidence"] < 0.5) for r in rows)
    assert all(r["is_stale"] is False for r in rows)
    names = {r["name"] for r in rows}
    assert "Arjun Mehta" in names and None not in names


def test_filters(client: TestClient, job_id: str) -> None:
    everyone = rankings(client, job_id)["rows"]
    cut = everyone[4]["match_percent"]
    assert [r["rank"] for r in rankings(client, job_id, min_score=cut)["rows"]] == [1, 2, 3, 4, 5]

    with_kafka = rankings(client, job_id, skill="kafka")["rows"]  # any spelling or alias
    assert 0 < len(with_kafka) < 14
    assert rankings(client, job_id, skill="Zz Unknown Skill")["rows"] == []

    found = rankings(client, job_id, search="mehta")["rows"]
    assert [r["name"] for r in found] == ["Arjun Mehta"]
    assert rankings(client, job_id, search="%")["rows"] == []  # a literal %, not a wildcard


def test_sorting(client: TestClient, job_id: str) -> None:
    by_name = [r["name"] for r in rankings(client, job_id, sort="name")["rows"]]
    assert by_name == sorted(by_name, key=str.lower)
    by_experience = [
        r["relevant_years"] for r in rankings(client, job_id, sort="relevant_experience")["rows"]
    ]
    assert by_experience == sorted(by_experience, reverse=True)
    assert client.get(f"/api/v1/jobs/{job_id}/rankings", params={"sort": "age"}).status_code == 422


def test_unknown_job_is_404(client: TestClient) -> None:
    assert client.get(f"/api/v1/jobs/{uuid.uuid4()}/rankings").status_code == 404


# --- Candidate detail ------------------------------------------------------------------------


def test_candidate_detail(client: TestClient, job_id: str) -> None:
    first = rankings(client, job_id)["rows"][0]
    response = client.get(f"/api/v1/jobs/{job_id}/candidates/{first['resume_id']}")

    assert response.status_code == 200
    detail = response.json()
    assert (detail["rank"], detail["match_percent"]) == (1, first["match_percent"])
    assert detail["email"] and detail["filename"].endswith((".pdf", ".docx"))
    assert set(detail["component_scores"]) == {"skills", "semantic", "experience", "education"}
    assert detail["requirement_matches"] and detail["matched_skills"]
    explanation = detail["explanation"]
    assert {"verdict", "summary", "breakdown", "strengths", "gaps", "notes", "details"} <= set(
        explanation
    )
    earned = sum(p["earned"] for p in explanation["breakdown"])
    assert earned == pytest.approx(round(detail["match_percent"], 1))
    # What the candidate page's tabs read
    assert {m["tier"] for m in detail["matched_skills"]} <= {
        "exact",
        "alias",
        "related",
        "contextual",
    }
    assert all(
        r["status"] in {"covered", "partial", "not_covered"} for r in detail["requirement_matches"]
    )
    roles = explanation["details"]["experience"]["roles"]
    assert roles and all(r["factor"] in (0, 0.5, 1) for r in roles)
    assert detail["educations"] and detail["educations"][0]["degree"]
    assert detail["name"] in detail["raw_text"]


def test_the_original_file_is_served_under_its_name(client: TestClient, job_id: str) -> None:
    row = rankings(client, job_id)["rows"][0]
    response = client.get(f"/api/v1/resumes/{row['resume_id']}/file")

    assert response.status_code == 200
    assert response.headers["content-type"] in {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    assert row["filename"] in response.headers["content-disposition"]
    assert response.headers["content-disposition"].startswith("inline")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.content[:4] in (b"%PDF", b"PK\x03\x04")
    assert client.get(f"/api/v1/resumes/{uuid.uuid4()}/file").status_code == 404


def test_a_resume_without_a_score_for_this_job_is_404(
    client: TestClient, job_id: str, seeded_session: Session
) -> None:
    failed = seeded_session.scalar(select(Resume.id).where(Resume.parse_error.is_not(None)))
    assert client.get(f"/api/v1/jobs/{job_id}/candidates/{failed}").status_code == 404
    other_job = client.post("/api/v1/jobs", json={"text": "We need Java and Docker skills."})
    resume_id = rankings(client, job_id)["rows"][0]["resume_id"]
    response = client.get(f"/api/v1/jobs/{other_job.json()['id']}/candidates/{resume_id}")
    assert response.status_code == 404


# --- Export -------------------------------------------------------------------------------------


def test_csv_export(client: TestClient, job_id: str, seeded_session: Session) -> None:
    # A name that a spreadsheet would run as a formula must come out as text.
    seeded_session.execute(
        update(Candidate)
        .where(Candidate.full_name == "Arjun Mehta")
        .values(full_name="=HYPERLINK(1)")
    )
    seeded_session.commit()

    response = client.get(f"/api/v1/jobs/{job_id}/rankings/export")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == (
        'attachment; filename="rankings-senior-backend-java-developer.csv"'
    )
    rows = list(csv.reader(io.StringIO(response.text)))
    assert rows[0][:3] == ["Rank", "Name", "Email"]
    assert len(rows) == 15 and [r[0] for r in rows[1:]] == [str(n) for n in range(1, 15)]
    assert "'=HYPERLINK(1)" in [r[1] for r in rows[1:]]
    assert all(not r[1].startswith("=") for r in rows[1:])


# --- Scoring runs and weights ------------------------------------------------------------------


def test_match_rescores_and_clears_stale(client: TestClient, job_id: str) -> None:
    patched = client.patch(f"/api/v1/jobs/{job_id}/requirements", json={"required_degree_level": 4})
    assert patched.status_code == 200
    assert all(r["is_stale"] for r in rankings(client, job_id)["rows"])

    response = client.post(f"/api/v1/jobs/{job_id}/match")

    assert response.status_code == 200
    assert response.json()["scored"] == 14
    rows = rankings(client, job_id)["rows"]
    assert not any(r["is_stale"] for r in rows)
    assert len(rows) == 14  # replaced, not added


def test_weights_change_the_totals(client: TestClient, job_id: str) -> None:
    only_skills = {"skills": 1, "semantic": 0, "experience": 0, "education": 0}
    response = client.patch(f"/api/v1/jobs/{job_id}/weights", json=only_skills)

    assert response.status_code == 200
    assert response.json()["weights"] == only_skills
    rows = rankings(client, job_id)["rows"]
    for row in rows:
        assert row["match_percent"] == pytest.approx(100 * row["skill_score"], abs=0.06)
    assert [r["match_percent"] for r in rows] == sorted(
        (r["match_percent"] for r in rows), reverse=True
    )
    job = client.get(f"/api/v1/jobs/{job_id}").json()
    assert job["scoring_weights"] == only_skills


def test_match_can_save_weights_too(client: TestClient, job_id: str) -> None:
    weights = {"skills": 2, "semantic": 1, "experience": 1, "education": 0}
    response = client.post(f"/api/v1/jobs/{job_id}/match", json={"weights": weights})
    assert (response.status_code, response.json()["weights"]) == (200, weights)


@pytest.mark.parametrize(
    "body",
    [
        {"skills": 0, "semantic": 0, "experience": 0, "education": 0},
        {"skills": -1, "semantic": 1, "experience": 1, "education": 1},
        {"skills": 1, "semantic": 1, "experience": 1},
        {"skills": 1, "semantic": 1, "experience": 1, "education": 1, "luck": 1},
    ],
    ids=["all-zero", "negative", "missing", "unknown"],
)
def test_bad_weights_are_422(client: TestClient, job_id: str, body: dict[str, float]) -> None:
    assert client.patch(f"/api/v1/jobs/{job_id}/weights", json=body).status_code == 422


def test_one_scoring_run_per_job_at_a_time(
    client: TestClient, job_id: str, migrated_engine: Engine
) -> None:
    key = func.hashtextextended(job_id, 0)
    with migrated_engine.connect() as other:  # another worker already scoring this job
        other.execute(select(func.pg_advisory_lock(key)))
        try:
            response = client.post(f"/api/v1/jobs/{job_id}/match")
        finally:
            other.execute(select(func.pg_advisory_unlock(key)))
            other.commit()
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "scoring_in_progress"


def test_scoring_needs_the_model(seeded_session: Session, store: FileStore, job_id: str) -> None:
    release = threading.Event()

    def slow_load() -> TextEncoder:
        release.wait(timeout=10)
        return FakeEncoder()

    loading = wire(make_api_app(seeded_session, ModelLoader(slow_load)), seeded_session, store)
    with TestClient(loading) as client:
        match = client.post(f"/api/v1/jobs/{job_id}/match")
        weights = client.patch(
            f"/api/v1/jobs/{job_id}/weights",
            json={"skills": 1, "semantic": 1, "experience": 1, "education": 1},
        )
        read = client.get(f"/api/v1/jobs/{job_id}/rankings")
        release.set()
    assert (match.status_code, weights.status_code) == (503, 503)
    assert read.status_code == 200  # reading stored results never needs the model
