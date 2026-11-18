"""Print the text the extractor gets from a file, exactly as later parsing steps see it.

python -m app.services.extraction ../sample_data/resumes/03_candidate_a_two_column.pdf
"""

import sys
from pathlib import Path

from app.core.config import get_settings
from app.services.extraction import JD_KINDS, ExtractionError, extract_text, validate_file


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    path = Path(argv[0])
    data = path.read_bytes()
    try:
        validated = validate_file(
            data, path.name, max_bytes=get_settings().max_file_size_bytes, allowed=JD_KINDS
        )
        extracted = extract_text(data, validated.kind)
    except ExtractionError as exc:
        print(f"[{exc.code}] {exc.message}", file=sys.stderr)
        return 1

    pages = f", {extracted.page_count} page(s)" if extracted.page_count else ""
    print(f"--- {path.name}: {extracted.kind}{pages}, {len(extracted.text)} characters ---")
    print(extracted.text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
