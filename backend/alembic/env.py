"""Alembic environment: migrations run against DATABASE_URL from app settings.

Usage (from backend/):
    alembic upgrade head
    alembic downgrade -1
    alembic revision --autogenerate --rev-id 0003 -m "short description"
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, create_engine, pool

from app.core.config import get_settings
from app.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _configure(**kwargs: object) -> None:
    context.configure(
        target_metadata=target_metadata,
        compare_type=True,  # detect column type changes in autogenerate
        compare_server_default=True,
        **kwargs,  # type: ignore[arg-type]
    )


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of executing it: `alembic upgrade head --sql`."""
    _configure(
        url=get_settings().database_url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_with_connection(connection: Connection) -> None:
    _configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Tests can pass an open connection via `config.attributes["connection"]`.
    existing = config.attributes.get("connection")
    if existing is not None:
        _run_with_connection(existing)
        return

    engine = create_engine(
        get_settings().database_url,
        poolclass=pool.NullPool,
        connect_args={"connect_timeout": 10},  # fail with an error instead of hanging
    )
    with engine.connect() as connection:
        _run_with_connection(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
