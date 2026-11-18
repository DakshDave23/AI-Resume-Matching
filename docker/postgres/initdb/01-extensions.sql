-- Runs once, when the Postgres data volume is first created.
-- The first Alembic migration (step 4) also runs this, so a database
-- created any other way (e.g. CI) ends up the same.
CREATE EXTENSION IF NOT EXISTS vector;
