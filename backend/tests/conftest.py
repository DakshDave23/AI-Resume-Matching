from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    # `with` runs the lifespan hook, exactly like a real server start.
    with TestClient(create_app()) as c:
        yield c
