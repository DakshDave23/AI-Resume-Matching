from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.database import DatabaseStatus, get_database_status
from app.main import create_app
from app.services.nlp.embedder import Embedder
from app.services.nlp.loader import ModelLoader
from tests.fakes import FakeEncoder

HEALTHY_DB = DatabaseStatus(reachable=True, pgvector_version="0.8.0")


@pytest.fixture
def app() -> FastAPI:
    """App with external dependencies faked, so unit tests run without Docker or torch.

    Tests can replace any override, e.g.
    `app.dependency_overrides[get_database_status] = lambda: DOWN`, or set
    `app.state.model_loader` to a loader that is still loading or fails.
    """
    app = create_app()
    app.dependency_overrides[get_database_status] = lambda: HEALTHY_DB
    app.state.model_loader = ModelLoader(FakeEncoder)
    app.state.resume_unfinished_batches = False
    return app


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    # `with` runs the lifespan hook, exactly like a real server start.
    with TestClient(app) as c:
        app.state.model_loader.wait(timeout=5)  # the fake loads instantly, but in a thread
        yield c


@pytest.fixture(scope="session")
def real_embedder() -> Embedder:
    """The real model, loaded once per test run (tests using it are marked `model`)."""
    return Embedder(get_settings().embedding_model)
