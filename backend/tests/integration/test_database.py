"""Talks to the real Postgres from docker-compose. Skipped when it isn't running."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import get_database_status, get_engine
from app.main import create_app

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module", autouse=True)
def require_database() -> Iterator[None]:
    if not get_database_status().reachable:
        pytest.skip("Postgres is not reachable; start it with: docker compose up -d --wait db")
    yield


def test_vector_extension_is_enabled_and_works() -> None:
    with get_engine().begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        # Cosine distance (<=>) between orthogonal vectors is 1; identical vectors is 0.
        orthogonal = conn.execute(text("SELECT '[1,0,0]'::vector <=> '[0,1,0]'::vector"))
        identical = conn.execute(text("SELECT '[1,2,3]'::vector <=> '[1,2,3]'::vector"))

        assert orthogonal.scalar_one() == pytest.approx(1.0)
        assert identical.scalar_one() == pytest.approx(0.0)


def test_health_reports_real_database_ready() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    checks = response.json()["checks"]
    assert checks["database"] == "ok"
    assert checks["pgvector"] != "missing"
