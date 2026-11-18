"""Show what the parser gets from a resume: contact, work, education, skills, sections.

python -m app.services.parsing ../sample_data/resumes/02_java_aliases.docx
"""

import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

from app.core.config import get_settings
from app.services.extraction import ExtractionError, extract_text, validate_file
from app.services.parsing.contact import extract_contact
from app.services.parsing.education import parse_education
from app.services.parsing.experience import parse_experience, skill_months
from app.services.parsing.sections import CONTACT, segment
from app.services.parsing.skills import get_skill_extractor


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

    today = date.today()
    work = parse_experience(
        segmentation.text_of("experience"), today=today, summary=segmentation.text_of("summary")
    )
    total = f"{work.total_months} months" if work.total_months is not None else "unknown"
    print(f"\n--- experience: {total} (from {work.source or '-'}), now: {work.current_title} ---")
    for role in work.roles:
        when = role.dates.text if role.dates else "undated"
        intern = "  [internship, not counted]" if role.is_internship else ""
        months = role.months(today)
        length = f" ({months} mo)" if months is not None else ""
        print(f"{role.title} | {role.company} | {role.location or '-'} | {when}{length}{intern}")

    education = parse_education(segmentation.text_of("education"))
    level = education.highest_level
    print(f"\n--- education: highest {level.name.lower() if level is not None else '-'} ---")
    for entry in education.entries:
        print(f"{entry.degree} | {entry.field or '-'} | {entry.institution or '-'} | {entry.year}")

    skills = get_skill_extractor().extract_resume(segmentation)
    used = skill_months(work, get_skill_extractor(), today=today)
    print(f"\n--- {len(skills.skills)} skills ---")
    for skill in skills.skills:
        sources = ", ".join(s.value for s in skill.sources)
        used_for = f"{used[skill.name]:>3} mo" if skill.name in used else "     -"
        print(f"{skill.name:<28} x{skill.mention_count} {used_for}  [{sources}]  {skill.evidence}")
    if skills.unmapped:
        print(f"unmapped: {', '.join(skills.unmapped)}")

    print(f"\n--- sections: {', '.join(segmentation.names())} ---")
    for section in segmentation.sections:
        header = f' (header: "{section.header}")' if section.header else ""
        print(f"\n[{section.name}]{header}")
        print(section.text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
