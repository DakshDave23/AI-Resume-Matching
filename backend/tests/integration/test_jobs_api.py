"""Step 19's "done when": a JD round-trips through the API (what Swagger calls).

Everything runs against the real database inside a transaction that is rolled back.
"""

import threading
import uuid
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import Job
from app.services.nlp.embedder import TextEncoder
from app.services.nlp.loader import ModelLoader
from tests.fakes import FakeEncoder
from tests.integration.conftest import make_api_app
from tests.integration.factories import make_batch, make_match, make_resume
from tests.samples import SAMPLES, jd, jd_text

pytestmark = pytest.mark.integration

JAVA_JD = jd_text(jd("backend_java"))
JOBS = "/api/v1/jobs"


def create(api: TestClient, **body: Any) -> dict[str, Any]:
    response = api.post(JOBS, json={"text": JAVA_JD} | body)
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def skills_by_name(job: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {s["name"]: s for s in job["skills"]}


def chips(job: dict[str, Any], **changes: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The job's skills as PATCH chips, with some changed (a dict) or removed (None)."""
    result = []
    for skill in job["skills"]:
        change = changes.get(skill["name"], {})
        if change is None:
            continue
        chip = {k: skill[k] for k in ("skill_id", "requirement_type", "min_years")}
        result.append(chip | change)
    return result


# --- Create and read -------------------------------------------------------------------


def test_a_pasted_jd_round_trips(api: TestClient) -> None:
    created = create(api)

    assert created["title"] == "Senior Backend Java Developer"
    assert (created["company"], created["location"], created["seniority"]) == (
        "Northwind Payments (synthetic)",
        "Bengaluru, India (Hybrid)",
        "senior",
    )
    assert (created["min_experience_years"], created["max_experience_years"]) == (4.0, None)
    assert created["required_degree_level"] == 3
    assert created["required_fields_of_study"] == ["Computer Science", "Information Technology"]
    assert created["status"] == "parsed"
    assert created["source_filename"] is None
    assert [s["name"] for s in created["skills"]] == [
        "Java", "Microservices", "PostgreSQL", "REST APIs", "Spring Boot",  # required, A-Z
        "AWS", "Docker", "Kafka",  # then preferred
    ]  # fmt: skip
    kafka = skills_by_name(created)["Kafka"]
    assert kafka | {"skill_id": 0} == {
        "skill_id": 0,
        "name": "Kafka",
        "category": "messaging",
        "is_custom": False,
        "requirement_type": "preferred",
        "weight": 0.5,
        "min_years": None,
        "source_text": "Familiarity with Kafka or other event streaming platforms.",
        "added_by": "parser",
    }
    assert [r["position"] for r in created["requirements"]] == list(range(16))
    assert created["requirements"][7]["category"] == "experience"

    fetched = api.get(f"{JOBS}/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == created


def test_the_recruiters_title_wins(api: TestClient) -> None:
    assert create(api, title="  Java Engineer (Payments)  ")["title"] == "Java Engineer (Payments)"


def test_a_jd_without_a_title_is_untitled(api: TestClient) -> None:
    job = create(api, text="We need someone who knows Java and Docker very well.")
    assert job["title"] == "Untitled job"
    assert {s["name"] for s in job["skills"]} == {"Java", "Docker"}


@pytest.mark.parametrize(
    "body",
    [{"text": "Java"}, {"text": ""}, {"text": "x" * 100_001}, {"text": JAVA_JD, "extra": 1}],
    ids=["too-short", "empty", "too-long", "unknown-field"],
)
def test_bad_create_requests_are_422(api: TestClient, body: dict[str, Any]) -> None:
    response = api.post(JOBS, json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_an_unknown_job_is_404(api: TestClient) -> None:
    response = api.get(f"{JOBS}/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"] == {
        "code": "not_found",
        "message": "Job not found",
        "details": None,
    }


def test_creating_a_job_needs_the_model(seeded_session: Session) -> None:
    release = threading.Event()

    def slow_load() -> TextEncoder:
        release.wait(timeout=10)
        return FakeEncoder()

    app = make_api_app(seeded_session, ModelLoader(slow_load))
    with TestClient(app) as client:
        response = client.post(JOBS, json={"text": JAVA_JD})
        release.set()
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "model_loading"


# --- Upload ---------------------------------------------------------------------------------


def upload(api: TestClient, name: str, data: bytes) -> Any:
    return api.post(f"{JOBS}/upload", files={"file": (name, data)})


def test_an_uploaded_jd_file_round_trips(api: TestClient) -> None:
    response = upload(api, "frontend.txt", jd_text(jd("frontend_react")).encode())
    assert response.status_code == 201, response.text
    job = response.json()
    assert (job["title"], job["source_filename"]) == ("Frontend React Developer", "frontend.txt")
    assert job["accepts_equivalent_experience"] is True
    assert api.get(f"{JOBS}/{job['id']}").json() == job


def test_a_pdf_jd_without_a_title_is_named_after_the_file(api: TestClient) -> None:
    resume_pdf = (SAMPLES / "resumes" / "01_senior_java_engineer.pdf").read_bytes()
    job = upload(api, "Backend Role.pdf", resume_pdf).json()
    assert job["source_filename"] == "Backend Role.pdf"
    assert job["title"]  # a PDF goes through the same extraction as resumes


@pytest.mark.parametrize(
    ("name", "data", "status", "code"),
    [
        ("jd.txt", b"", 400, "empty_file"),
        ("jd.exe", b"MZ\x90\x00", 415, "unsupported_type"),
        ("jd.pdf", b"not really a pdf", 415, "unsupported_type"),
        ("scan.pdf", (SAMPLES / "resumes" / "15_scanned_pdf.pdf").read_bytes(), 422, "scanned_pdf"),
        ("jd.txt", b"Java", 422, "no_text"),
    ],
    ids=["empty", "exe", "fake-pdf", "scanned", "too-little-text"],
)
def test_bad_uploads_say_why(
    api: TestClient, name: str, data: bytes, status: int, code: str
) -> None:
    response = upload(api, name, data)
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code


def test_an_oversized_upload_is_413(seeded_session: Session) -> None:
    app = make_api_app(seeded_session)
    app.dependency_overrides[get_settings] = lambda: Settings(max_file_size_mb=1)
    with TestClient(app) as client:
        app.state.model_loader.wait(timeout=5)
        response = upload(client, "big.txt", b"Java developer. " * 70_000)  # ~1.1 MB
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "file_too_large"


# --- List ----------------------------------------------------------------------------------


def test_jobs_are_listed_newest_first_with_counts(api: TestClient, seeded_session: Session) -> None:
    first = create(api, title="Zz First")
    second = create(api, title="Zz Second")
    job_row = seeded_session.get(Job, uuid.UUID(first["id"]))
    assert job_row is not None
    # Inside one test transaction now() never moves; in the app each request has its own.
    job_row.created_at -= timedelta(minutes=1)
    batch = make_batch(job_row, total_files=1)
    resume = make_resume(batch)
    seeded_session.add_all([batch, resume, make_match(job_row, resume)])
    seeded_session.flush()

    listed = api.get(JOBS, params={"limit": 100}).json()
    mine = {item["title"]: item for item in listed["items"] if item["title"].startswith("Zz ")}

    assert list(mine) == ["Zz Second", "Zz First"]  # newest first
    assert mine["Zz First"]["resume_count"] == 1
    assert mine["Zz First"]["top_score"] == 83.1
    assert (mine["Zz Second"]["resume_count"], mine["Zz Second"]["top_score"]) == (0, None)
    assert listed["total"] >= 2 and listed["limit"] == 100
    assert second["id"] in {item["id"] for item in listed["items"]}


def test_list_paging(api: TestClient) -> None:
    for n in range(3):
        create(api, title=f"Zz Page {n}")
    page = api.get(JOBS, params={"limit": 2, "offset": 1}).json()
    assert len(page["items"]) == 2 and page["offset"] == 1
    assert api.get(JOBS, params={"limit": 0}).status_code == 422


# --- Recruiter edits ---------------------------------------------------------------------------


def patch(api: TestClient, job: dict[str, Any], body: dict[str, Any]) -> Any:
    return api.patch(f"{JOBS}/{job['id']}/requirements", json=body)


def test_editing_skill_chips(api: TestClient) -> None:
    job = create(api)
    kept = chips(
        job,
        Kafka={"requirement_type": "required", "min_years": 2},  # moved to required
        AWS=None,  # removed
    )
    added = [
        {"name": "k8s", "requirement_type": "preferred"},  # an alias
        {"name": "Zz Quantum Widgets", "category": "devops", "requirement_type": "required"},
    ]
    body = {"skills": [*kept, *added]}
    response = patch(api, job, body)
    assert response.status_code == 200, response.text
    skills = skills_by_name(response.json())

    assert "AWS" not in skills
    assert skills["Kafka"] | {"skill_id": 0} == skills_by_name(job)["Kafka"] | {
        "skill_id": 0,
        "requirement_type": "required",
        "weight": 1.0,
        "min_years": 2.0,
        "added_by": "recruiter",
    }
    assert skills["Kubernetes"]["added_by"] == "recruiter"
    assert skills["Java"]["added_by"] == "parser"  # untouched chips stay the parser's
    custom = skills["Zz Quantum Widgets"]
    assert (custom["is_custom"], custom["category"], custom["requirement_type"]) == (
        True,
        "devops",
        "required",
    )
    assert api.get(f"{JOBS}/{job['id']}").json()["skills"] == response.json()["skills"]


def test_a_custom_skill_is_reused_not_duplicated(api: TestClient) -> None:
    job = create(api)
    chip = {"name": "Zz Quantum Widgets", "requirement_type": "required"}
    first = patch(api, job, {"skills": [chip]}).json()
    second = patch(api, job, {"skills": [chip | {"name": "zz quantum widgets"}]}).json()
    assert first["skills"][0]["skill_id"] == second["skills"][0]["skill_id"]


def test_editing_years_degree_and_fields_leaves_skills_alone(api: TestClient) -> None:
    job = create(api)
    response = patch(
        api,
        job,
        {
            "min_experience_years": 3,
            "max_experience_years": 6.5,
            "required_degree_level": 4,
            "required_fields_of_study": ["Computer Science", "Statistics", "Computer Science"],
            "accepts_equivalent_experience": True,
        },
    )
    edited = response.json()
    assert (edited["min_experience_years"], edited["max_experience_years"]) == (3.0, 6.5)
    assert edited["required_degree_level"] == 4
    assert edited["required_fields_of_study"] == ["Computer Science", "Statistics"]
    assert edited["accepts_equivalent_experience"] is True
    assert edited["skills"] == job["skills"]


def test_clearing_a_value_with_null(api: TestClient) -> None:
    job = create(api)
    edited = patch(api, job, {"min_experience_years": None, "required_degree_level": None}).json()
    assert (edited["min_experience_years"], edited["required_degree_level"]) == (None, None)


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"skills": [{"skill_id": 999_999_999, "requirement_type": "required"}]}, "unknown_skill"),
        (
            {"skills": [{"name": "Java", "requirement_type": "required"}] * 2},
            "duplicate_skill",
        ),
        ({"max_experience_years": 2}, "invalid_experience_range"),  # below the JD's 4
        ({"min_experience_years": 5, "max_experience_years": 2}, "validation_error"),
        ({"skills": [{"requirement_type": "required"}]}, "validation_error"),
        ({"skills": None}, "validation_error"),
        ({"required_degree_level": 9}, "validation_error"),
        ({"weights": {}}, "validation_error"),
    ],
    ids=[
        "unknown-id", "duplicate", "max-below-saved-min", "max-below-min", "no-reference",
        "null-skills", "bad-degree", "unknown-field",
    ],
)  # fmt: skip
def test_bad_edits_are_422(api: TestClient, body: dict[str, Any], code: str) -> None:
    job = create(api)
    response = patch(api, job, body)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == code
    assert api.get(f"{JOBS}/{job['id']}").json() == job  # nothing was saved


def test_an_edit_marks_existing_scores_stale(api: TestClient, seeded_session: Session) -> None:
    job = create(api)
    job_row = seeded_session.get(Job, uuid.UUID(job["id"]))
    assert job_row is not None
    batch = make_batch(job_row)
    resume = make_resume(batch)
    match = make_match(job_row, resume)
    seeded_session.add_all([batch, resume, match])
    seeded_session.flush()

    assert patch(api, job, {"required_degree_level": 4}).status_code == 200

    seeded_session.refresh(match)
    assert match.is_stale is True


def test_edits_without_new_skills_work_while_the_model_loads(seeded_session: Session) -> None:
    ready = make_api_app(seeded_session)
    with TestClient(ready) as client:
        ready.state.model_loader.wait(timeout=5)
        job = create(client)

    release = threading.Event()

    def slow_load() -> TextEncoder:
        release.wait(timeout=10)
        return FakeEncoder()

    loading = make_api_app(seeded_session, ModelLoader(slow_load))
    with TestClient(loading) as client:
        moved = patch(client, job, {"skills": chips(job, Docker={"requirement_type": "required"})})
        new_skill = {"name": "Zz New", "requirement_type": "required"}
        custom = patch(client, job, {"skills": [new_skill]})
        release.set()
    assert moved.status_code == 200
    assert custom.status_code == 503
    assert custom.json()["error"]["code"] == "model_loading"
