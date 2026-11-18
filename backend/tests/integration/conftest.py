"""Fixtures for tests that need the real Postgres from docker-compose."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.core.database import get_database_status, get_db, get_engine
from app.main import create_app
from app.repositories.skills import upsert_taxonomy
from app.services.nlp.loader import ModelLoader
from app.services.nlp.taxonomy import get_taxonomy
from tests.fakes import FakeEncoder

BACKEND_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def migrated_engine() -> Engine:
    """Skip if Postgres is down; otherwise bring the schema to the latest migration once."""
    if not get_database_status().reachable:
        pytest.skip("Postgres is not reachable; start it with: docker compose up -d --wait db")
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    return get_engine()


@pytest.fixture
def db_session(migrated_engine: Engine) -> Iterator[Session]:
    """A session inside a transaction that is always rolled back.

    Nothing a test writes survives, so tests can't affect each other or your dev data.
    `join_transaction_mode="create_savepoint"` lets a test call session.rollback()
    (e.g. after an expected IntegrityError) without ending the outer transaction.
    """
    with migrated_engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            transaction.rollback()


def make_api_app(session: Session, loader: ModelLoader | None = None) -> FastAPI:
    """The real app on the test's rolled-back session, with the fake encoder."""
    app = create_app()

    def request_session() -> Iterator[Session]:
        try:
            yield session
        finally:
            # Like closing a request's own session: whatever a failed request left
            # uncommitted is discarded (only back to the last commit's savepoint).
            session.rollback()

    app.dependency_overrides[get_db] = request_session
    app.state.model_loader = loader or ModelLoader(FakeEncoder)
    return app


@pytest.fixture
def seeded_session(db_session: Session) -> Session:
    """The taxonomy inside the test's transaction: a fresh CI database has none."""
    upsert_taxonomy(db_session, get_taxonomy())
    return db_session


@pytest.fixture
def api(seeded_session: Session) -> Iterator[TestClient]:
    """A client for the real API whose writes all roll back after the test.

    Routes call session.commit(); with join_transaction_mode="create_savepoint"
    that only releases a savepoint inside the test's outer transaction.
    """
    app = make_api_app(seeded_session)
    with TestClient(app) as client:
        app.state.model_loader.wait(timeout=5)
        yield client
