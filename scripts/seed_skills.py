"""Seed the skills table from backend/app/data/skills_taxonomy.json, with embeddings.

Run with the backend's virtualenv Python (the backend is installed in it with
`pip install -e`, so `app` is importable from anywhere):

    backend/.venv/Scripts/python scripts/seed_skills.py            # Windows
    backend/.venv/bin/python scripts/seed_skills.py                # macOS/Linux
    ... scripts/seed_skills.py --check                             # validate only, no DB
    ... scripts/seed_skills.py --reembed                           # after changing EMBEDDING_MODEL

Safe to run repeatedly: existing skills are updated in place, never duplicated.
Then every skill without a vector (new, renamed or recruiter-added) is embedded
with EMBEDDING_MODEL, which is downloaded on first use (about 90 MB).
Exit codes: 0 ok, 1 invalid taxonomy, 2 database unreachable or not migrated,
3 embedding model failed to load (the taxonomy itself was still saved).
"""

import argparse
import sys
from collections import Counter

from pydantic import ValidationError
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.core.config import get_settings
from app.core.database import get_sessionmaker
from app.repositories.skills import (
    count_skills_without_embedding,
    fill_skill_embeddings,
    upsert_taxonomy,
)
from app.services.nlp.embedder import Embedder, EmbeddingError
from app.services.nlp.taxonomy import TAXONOMY_PATH, load_taxonomy


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="validate the file only")
    parser.add_argument(
        "--reembed", action="store_true", help="embed every skill again, not only missing ones"
    )
    args = parser.parse_args()

    try:
        taxonomy = load_taxonomy()
    except ValidationError as exc:
        print(f"Invalid taxonomy in {TAXONOMY_PATH}:\n{exc}", file=sys.stderr)
        return 1

    per_category = Counter(s.category.value for s in taxonomy.skills)
    terms = sum(len(s.terms) for s in taxonomy.skills)
    print(f"Taxonomy v{taxonomy.version}: {len(taxonomy.skills)} skills, {terms} terms")
    print("  " + ", ".join(f"{cat} {n}" for cat, n in per_category.most_common()))

    if args.check:
        print("OK (validation only, database not touched)")
        return 0

    try:
        with get_sessionmaker()() as session, session.begin():
            result = upsert_taxonomy(session, taxonomy)
    except OperationalError:
        print(
            "Cannot reach Postgres. Start it with: docker compose up -d --wait db", file=sys.stderr
        )
        return 2
    except ProgrammingError as exc:
        print(f"Database not ready (run `alembic upgrade head`?): {exc.orig}", file=sys.stderr)
        return 2

    print(
        f"Seeded skills: {result.inserted} inserted, {result.updated} updated, "
        f"{result.unchanged} unchanged"
    )

    if not args.reembed:
        with get_sessionmaker()() as session:
            if count_skills_without_embedding(session) == 0:
                print("Embedded skills: none missing (use --reembed after changing the model)")
                return 0

    settings = get_settings()
    print(f"Loading {settings.embedding_model} ...")
    try:
        embedder = Embedder(settings.embedding_model, batch_size=settings.embedding_batch_size)
    except (OSError, EmbeddingError) as exc:
        print(f"Cannot load the embedding model: {exc}", file=sys.stderr)
        return 3
    with get_sessionmaker()() as session, session.begin():
        embedded = fill_skill_embeddings(session, embedder, everything=args.reembed)
    print(f"Embedded skills: {embedded} ({'all' if args.reembed else 'missing only'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
