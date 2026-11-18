from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# all-MiniLM-L6-v2 and bge-small-en-v1.5 both produce 384-dim vectors.
# Switching to a model with another size needs a migration for every VECTOR column.
EMBEDDING_DIM = 384

# Deterministic constraint names, so Alembic can drop/alter them by name later.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
