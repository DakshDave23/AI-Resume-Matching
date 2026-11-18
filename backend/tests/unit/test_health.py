import threading
from collections.abc import Callable

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app import __version__
from app.api.deps import get_embedder
from app.core.database import DatabaseStatus, get_database_status
from app.services.nlp.embedder import TextEncoder
from app.services.nlp.loader import ModelLoader
from tests.fakes import FakeEncoder

READY = {"database": "ok", "pgvector": "0.8.0", "embedding_model": "ok"}


def test_health_returns_ok_when_database_ready(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__
    assert body["checks"] == READY


@pytest.mark.parametrize(
    ("db_status", "expected_checks"),
    [
        (
            DatabaseStatus(reachable=False, pgvector_version=None),
            {"database": "unavailable", "pgvector": "missing", "embedding_model": "ok"},
        ),
        (
            DatabaseStatus(reachable=True, pgvector_version=None),
            {"database": "ok", "pgvector": "missing", "embedding_model": "ok"},
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


# --- The embedding model ----------------------------------------------------------


def blocked_loader(release: threading.Event) -> ModelLoader:
    """A loader that stays "loading" until `release` is set."""

    def load() -> TextEncoder:
        release.wait(timeout=10)
        return FakeEncoder()

    return ModelLoader(load)


def test_health_is_503_while_the_model_loads_then_200(app: FastAPI) -> None:
    release = threading.Event()
    app.state.model_loader = blocked_loader(release)

    with TestClient(app) as client:  # the API serves while the model loads
        loading = client.get("/api/v1/health")
        release.set()
        app.state.model_loader.wait(timeout=5)
        ready = client.get("/api/v1/health")

    assert loading.status_code == 503
    assert loading.json()["checks"]["embedding_model"] == "loading"
    assert ready.status_code == 200
    assert ready.json()["checks"] == READY


def broken_load() -> TextEncoder:
    raise OSError("no such model: not-a-model")


def test_health_reports_a_model_that_failed_to_load(app: FastAPI) -> None:
    app.state.model_loader = ModelLoader(broken_load)
    with TestClient(app) as client:
        app.state.model_loader.wait(timeout=5)
        response = client.get("/api/v1/health")

    assert response.status_code == 503
    assert response.json()["checks"]["embedding_model"] == "failed"
    assert app.state.model_loader.error == "OSError: no such model: not-a-model"


def test_the_model_loads_once_however_many_requests(app: FastAPI) -> None:
    loads: list[int] = []

    def counting_load() -> TextEncoder:
        loads.append(1)
        return FakeEncoder()

    app.state.model_loader = ModelLoader(counting_load)
    with TestClient(app) as client:
        app.state.model_loader.start()  # a second start is ignored
        app.state.model_loader.wait(timeout=5)
        for _ in range(5):
            assert client.get("/api/v1/health").status_code == 200
    assert loads == [1]


@pytest.mark.parametrize(
    ("make_loader", "code"),
    [
        (lambda: blocked_loader(threading.Event()), "model_loading"),
        (lambda: ModelLoader(broken_load), "model_unavailable"),
    ],
    ids=["loading", "failed"],
)
def test_routes_needing_the_embedder_answer_503_until_it_is_ready(
    app: FastAPI, make_loader: Callable[[], ModelLoader], code: str
) -> None:
    @app.get("/test-embed")
    def embed(encoder: TextEncoder = Depends(get_embedder)) -> dict[str, int]:
        return {"dims": int(encoder.encode(["hello"]).shape[1])}

    app.state.model_loader = make_loader()
    with TestClient(app) as client:
        if code == "model_unavailable":
            app.state.model_loader.wait(timeout=5)
        response = client.get("/test-embed")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == code


def test_routes_get_the_loaded_embedder(app: FastAPI, client: TestClient) -> None:
    @app.get("/test-embed")
    def embed(encoder: TextEncoder = Depends(get_embedder)) -> dict[str, int]:
        return {"dims": int(encoder.encode(["hello"]).shape[1])}

    assert client.get("/test-embed").json() == {"dims": 384}
