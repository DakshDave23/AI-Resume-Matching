"""SQLAlchemy engine, sessions, and the database readiness check."""

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def get_engine() -> Engine:
    """One engine (and connection pool) per process, created on first use."""
    return create_engine(
        get_settings().database_url,
        pool_pre_ping=True,  # drop dead connections, e.g. after the DB container restarts
        connect_args={"connect_timeout": 3},  # fail fast instead of hanging requests
    )


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed."""
    with get_sessionmaker()() as session:
        yield session


@dataclass(frozen=True)
class DatabaseStatus:
    reachable: bool
    pgvector_version: str | None  # None when the extension is not installed


def get_database_status() -> DatabaseStatus:
    """FastAPI dependency used by /health; overridden in unit tests."""
    try:
        with get_engine().connect() as conn:
            version = conn.execute(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            ).scalar_one_or_none()
        return DatabaseStatus(reachable=True, pgvector_version=version)
    except SQLAlchemyError as exc:
        # Log the reason server-side only; /health just says "unavailable".
        logger.warning("Database health check failed: %s", exc.__class__.__name__)
        return DatabaseStatus(reachable=False, pgvector_version=None)
