"""Write the API's OpenAPI schema to frontend/openapi.json (design doc §9, data layer).

The frontend generates its TypeScript types from this file with openapi-typescript,
so the two sides can't drift apart. No server needed: the schema comes from the app
object itself.

Usage (from the repo root, with the backend virtualenv), or `make types`:
    backend/.venv/Scripts/python scripts/export_openapi.py      # Windows
    backend/.venv/bin/python scripts/export_openapi.py          # macOS/Linux
"""

import json
import sys
from pathlib import Path

from app.main import create_app

OUT = Path(__file__).resolve().parents[1] / "frontend" / "openapi.json"


def main() -> int:
    schema = create_app().openapi()
    OUT.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote {OUT} ({len(schema['paths'])} paths)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
