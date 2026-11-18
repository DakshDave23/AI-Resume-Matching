"""Seed the skills table from backend/app/data/skills_taxonomy.json.

Run with the backend's virtualenv Python (the backend is installed in it with
`pip install -e`, so `app` is importable from anywhere):

    backend/.venv/Scripts/python scripts/seed_skills.py            # Windows
    backend/.venv/bin/python scripts/seed_skills.py                # macOS/Linux
    ... scripts/seed_skills.py --check                             # validate only, no DB

Safe to run repeatedly: existing skills are updated in place, never duplicated.
Exit codes: 0 ok, 1 invalid taxonomy, 2 database unreachable or not migrated.
"""

import argparse
import sys
from collections import Counter

from pydantic import ValidationError
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.core.database import get_sessionmaker
from app.repositories.skills import upsert_taxonomy
from app.services.nlp.taxonomy import TAXONOMY_PATH, load_taxonomy


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="validate the file only")
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
