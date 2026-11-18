"""Step 12's "done when": persona 9 is not double counted.

Every role (title, company, dates, current, internship, precision), the total
months, its source and the current title are checked against
sample_data/ground_truth.json, using its as-of date as "today".
"""

import pytest

from app.services.parsing.dates import YearMonth
from app.services.parsing.experience import WorkHistory, parse_experience
from tests.samples import AS_OF, TEXT_RESUMES, Sample, resume_id, resume_sections, text_resume


def history_of(resume: Sample) -> WorkHistory:
    sections = resume_sections(resume)
    return parse_experience(
        sections.text_of("experience"), today=AS_OF, summary=sections.text_of("summary")
    )


def month(value: YearMonth | None) -> str | None:
    return f"{value.year}-{value.month:02d}" if value else None


@pytest.mark.parametrize("resume", TEXT_RESUMES, ids=resume_id)
def test_roles_match_ground_truth(resume: Sample) -> None:
    found = [
        {
            "title": role.title,
            "company": role.company,
            "start": month(role.dates.start) if role.dates else None,
            "end": month(role.dates.end) if role.dates else None,
            "is_current": role.is_current,
            "is_internship": role.is_internship,
            "date_precision": role.dates.precision if role.dates else None,
        }
        for role in history_of(resume).roles
    ]
    assert found == resume["roles"]


@pytest.mark.parametrize("resume", TEXT_RESUMES, ids=resume_id)
def test_totals_match_ground_truth(resume: Sample) -> None:
    result = history_of(resume)
    assert result.total_months == resume["total_experience_months"]
    assert result.source == resume["experience_source"]
    assert result.current_title == resume["current_title"]


def test_persona_9_overlapping_roles_are_not_double_counted() -> None:
    result = history_of(text_resume(9))

    summed = sum(role.months(AS_OF) or 0 for role in result.roles)
    assert summed == 137  # 81 + 24 + 32: the freelance years sit inside the bank job
    assert result.total_months == 113
