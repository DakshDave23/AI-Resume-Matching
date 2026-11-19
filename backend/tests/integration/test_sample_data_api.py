"""Step 37: "Load sample data" makes the demo job and batch; failed files show their reason.

The real API and database in a rolled-back transaction, the fake encoder for the model.
TestClient runs the background parse before `post()` returns.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.services.storage import FileStore
from tests.integration.conftest import make_api_app, wire

pytestmark = pytest.mark.integration

SCANNED_REASON = "Looks like a scanned image; OCR is not enabled."


@pytest.fixture
def client(seeded_session: Session, store: FileStore) -> Iterator[TestClient]:
    app = wire(make_api_app(seeded_session), seeded_session, store)
    with TestClient(app) as c:
        app.state.model_loader.wait(timeout=5)
        yield c


def test_sample_data_creates_the_demo_job_and_parses_the_samples(
    client: TestClient, store: FileStore
) -> None:
    response = client.post("/api/v1/sample-data")

    assert response.status_code == 202
    created = response.json()
    assert (created["total_files"], created["rejected"]) == (15, [])
    job = client.get(f"/api/v1/jobs/{created['job_id']}").json()
    assert job["title"] == "Senior Backend Java Developer"
    assert job["source_filename"] == "backend_java_developer.txt"

    batch = client.get(f"/api/v1/batches/{created['batch_id']}").json()
    assert (batch["processed_files"], batch["failed_files"]) == (14, 1)
    assert len(list(store.root.iterdir())) == 15

    # The rankings list the 14 scored and say why the 15th isn't there.
    rankings = client.get(f"/api/v1/jobs/{created['job_id']}/rankings").json()
    assert rankings["total"] == 14
    assert rankings["not_ranked"] == [
        {
            "resume_id": rankings["not_ranked"][0]["resume_id"],
            "filename": "15_scanned_pdf.pdf",
            "parse_status": "failed",
            "parse_error": SCANNED_REASON,
        }
    ]
    # Filters narrow the rows, never the unranked list.
    filtered = client.get(
        f"/api/v1/jobs/{created['job_id']}/rankings", params={"search": "nobody"}
    ).json()
    assert (filtered["total"], len(filtered["not_ranked"])) == (0, 1)


def test_a_server_without_sample_data_says_so(
    seeded_session: Session, store: FileStore, tmp_path: Path
) -> None:
    app = wire(make_api_app(seeded_session), seeded_session, store)
    app.dependency_overrides[get_settings] = lambda: Settings(sample_data_dir=tmp_path)
    with TestClient(app) as client:
        app.state.model_loader.wait(timeout=5)
        response = client.post("/api/v1/sample-data")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "no_sample_data"
