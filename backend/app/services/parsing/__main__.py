"""Show what the parser gets from a resume: contact details, then its sections.

python -m app.services.parsing ../sample_data/resumes/02_java_aliases.docx
"""

import sys
from dataclasses import asdict
from pathlib import Path

from app.core.config import get_settings
from app.services.extraction import ExtractionError, extract_text, validate_file
from app.services.parsing.contact import extract_contact
from app.services.parsing.sections import CONTACT, segment


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    path = Path(argv[0])
    data = path.read_bytes()
    try:
        validated = validate_file(data, path.name, max_bytes=get_settings().max_file_size_bytes)
        text = extract_text(data, validated.kind).text
    except ExtractionError as exc:
        print(f"[{exc.code}] {exc.message}", file=sys.stderr)
        return 1

    segmentation = segment(text)
    contact = extract_contact(
        segmentation.text_of(CONTACT), text, region=get_settings().phone_default_region
    )
    print(f"--- {path.name} ---")
    for field, value in asdict(contact).items():
        print(f"{field:>13}: {value if value is not None else '-'}")

    print(f"\n--- sections: {', '.join(segmentation.names())} ---")
    for section in segmentation.sections:
        header = f' (header: "{section.header}")' if section.header else ""
        print(f"\n[{section.name}]{header}")
        print(section.text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
