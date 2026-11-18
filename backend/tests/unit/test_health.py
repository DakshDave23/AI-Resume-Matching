import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import __version__
from app.core.database import DatabaseStatus, get_database_status


def test_health_returns_ok_when_database_ready(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__
    assert body["checks"] == {"database": "ok", "pgvector": "0.8.0"}


@pytest.mark.parametrize(
    ("db_status", "expected_checks"),
    [
        (
            DatabaseStatus(reachable=False, pgvector_version=None),
            {"database": "unavailable", "pgvector": "missing"},
        ),
        (
            DatabaseStatus(reachable=True, pgvector_version=None),
            {"database": "ok", "pgvector": "missing"},
        ),
    ],
    ids=["database-down", "pgvector-missing"],
)
def test_health_returns_503_when_not_ready(
    app: FastAPI,
    client: TestClient,
    db_status: DatabaseStatus,
    expected_checks: dict[str, str],
) -> None:
    app.dependency_overrides[get_database_status] = lambda: db_status

    response = client.get("/api/v1/health")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.json()["checks"] == expected_checks


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "Not Found", "details": None}
    }


def test_cors_allows_only_configured_frontend_origin(client: TestClient) -> None:
    allowed = client.get("/api/v1/health", headers={"Origin": "http://localhost:5173"})
    blocked = client.get("/api/v1/health", headers={"Origin": "https://evil.example.com"})

    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "access-control-allow-origin" not in blocked.headers
