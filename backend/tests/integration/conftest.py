"""Fixtures for tests that need the real Postgres from docker-compose."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.core.database import get_database_status, get_engine

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
