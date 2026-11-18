"""Show what the parser gets from a resume (contact, work, education, skills, chunks, sections)
or, with --jd, from a job description (title, skills, years, degree, requirements).

python -m app.services.parsing ../sample_data/resumes/02_java_aliases.docx
python -m app.services.parsing --jd ../sample_data/jds/backend_java_developer.txt
"""

import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

from app.core.config import get_settings
from app.models.enums import RequirementType
from app.services.extraction import JD_KINDS, ExtractionError, extract_text, validate_file
from app.services.parsing.chunker import chunk_resume
from app.services.parsing.jd_parser import parse_job
from app.services.parsing.resume_parser import parse_resume


def main(argv: list[str]) -> int:
    is_jd = argv[:1] == ["--jd"]
    if is_jd:
        argv = argv[1:]
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    path = Path(argv[0])
    data = path.read_bytes()
    try:
        max_bytes = get_settings().max_file_size_bytes
        if is_jd:
            validated = validate_file(data, path.name, max_bytes=max_bytes, allowed=JD_KINDS)
        else:
            validated = validate_file(data, path.name, max_bytes=max_bytes)
        text = extract_text(data, validated.kind).text
    except ExtractionError as exc:
        print(f"[{exc.code}] {exc.message}", file=sys.stderr)
        return 1
    if is_jd:
        show_job(path.name, text)
    else:
        show_resume(path.name, text)
    return 0


def show_job(name: str, text: str) -> None:
    job = parse_job(text)
    print(f"--- {name} ---")
    print(f"     title: {job.title or '-'} ({job.seniority.value})")
    print(f"   company: {job.company or '-'}")
    print(f"  location: {job.location or '-'}")
    years = "-" if job.min_experience_years is None else f"{job.min_experience_years:g}"
    if job.max_experience_years is not None:
        years += f" to {job.max_experience_years:g}"
    print(f"experience: {years} years")
    level = job.degree_level.name.lower() if job.degree_level is not None else "-"
    soft = " (or equivalent experience)" if job.accepts_equivalent_experience else ""
    print(f"    degree: {level}{soft}; fields: {', '.join(job.fields_of_study) or '-'}")

    for kind in (RequirementType.REQUIRED, RequirementType.PREFERRED):
        skills = [s for s in job.skills if s.requirement_type == kind]
        print(f"\n--- {len(skills)} {kind.value} skills ---")
        for skill in skills:
            min_years = f"{skill.min_years:g}+ yrs" if skill.min_years is not None else "-"
            print(f"{skill.name:<24} {min_years:>8}  {skill.source_text}")
    if job.unmapped:
        print(f"unmapped: {', '.join(job.unmapped)}")

    print(f"\n--- {len(job.requirements)} requirements ---")
    for position, req in enumerate(job.requirements):
        print(f"{position:>2} {req.requirement_type.value:<9} {req.category.value:<14} {req.text}")
    print(f"\n--- sections: {', '.join(job.segmentation.names())} ---")


def show_resume(name: str, text: str) -> None:
    today = date.today()
    parsed = parse_resume(text, today=today, region=get_settings().phone_default_region)
    print(f"--- {name} ---")
    for field, value in asdict(parsed.contact).items():
        print(f"{field:>13}: {value if value is not None else '-'}")
    failed = [check for check, ok in parsed.checks.items() if not ok]
    review = "  [needs review]" if parsed.needs_review else ""
    print(f"   confidence: {parsed.confidence:.2f}{review}  missing: {', '.join(failed) or '-'}")

    work = parsed.work
    total = f"{work.total_months} months" if work.total_months is not None else "unknown"
    print(f"\n--- experience: {total} (from {work.source or '-'}), now: {work.current_title} ---")
    for role in work.roles:
        when = role.dates.text if role.dates else "undated"
        intern = "  [internship, not counted]" if role.is_internship else ""
        months = role.months(today)
        length = f" ({months} mo)" if months is not None else ""
        print(f"{role.title} | {role.company} | {role.location or '-'} | {when}{length}{intern}")

    level = parsed.education.highest_level
    print(f"\n--- education: highest {level.name.lower() if level is not None else '-'} ---")
    for entry in parsed.education.entries:
        print(f"{entry.degree} | {entry.field or '-'} | {entry.institution or '-'} | {entry.year}")

    skills, used = parsed.skills, parsed.skill_months
    print(f"\n--- {len(skills.skills)} skills ---")
    for skill in skills.skills:
        sources = ", ".join(s.value for s in skill.sources)
        used_for = f"{used[skill.name]:>3} mo" if skill.name in used else "     -"
        print(f"{skill.name:<28} x{skill.mention_count} {used_for}  [{sources}]  {skill.evidence}")
    if skills.unmapped:
        print(f"unmapped: {', '.join(skills.unmapped)}")

    chunks = chunk_resume(parsed.sections, parsed.work)
    print(f"\n--- {len(chunks)} chunks (what gets embedded) ---")
    for index, chunk in enumerate(chunks):
        print(f"\n[{index}: {chunk.section}, {chunk.words} words]")
        print(chunk.text)

    print(f"\n--- sections: {', '.join(parsed.sections.names())} ---")
    for section in parsed.sections.sections:
        header = f' (header: "{section.header}")' if section.header else ""
        print(f"\n[{section.name}]{header}")
        print(section.text)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
