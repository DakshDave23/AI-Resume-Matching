from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import DatabaseStatus, get_database_status
from app.main import create_app

HEALTHY_DB = DatabaseStatus(reachable=True, pgvector_version="0.8.0")


@pytest.fixture
def app() -> FastAPI:
    """App with external dependencies faked, so unit tests run without Docker.

    Tests can replace any override, e.g.
    `app.dependency_overrides[get_database_status] = lambda: DOWN`.
    """
    app = create_app()
    app.dependency_overrides[get_database_status] = lambda: HEALTHY_DB
    return app


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    # `with` runs the lifespan hook, exactly like a real server start.
    with TestClient(app) as c:
        yield c
