"""Step 13's "done when": degree levels right on every text sample.

Each entry's degree, field, institution, year and level, and the resume's
highest level, are checked against sample_data/ground_truth.json.
"""

import pytest

from app.services.parsing.education import EducationResult, parse_education
from tests.samples import TEXT_RESUMES, Sample, resume_id, resume_sections, text_resume


def education_of(resume: Sample) -> EducationResult:
    return parse_education(resume_sections(resume).text_of("education"))


@pytest.mark.parametrize("resume", TEXT_RESUMES, ids=resume_id)
def test_highest_degree_level(resume: Sample) -> None:
    assert education_of(resume).highest_level == resume["degree_level"]


@pytest.mark.parametrize("resume", TEXT_RESUMES, ids=resume_id)
def test_entries_match_ground_truth(resume: Sample) -> None:
    found = [
        {
            "degree": e.degree,
            "field": e.field,
            "institution": e.institution,
            "year": e.year,
            "level": e.level,
        }
        for e in education_of(resume).entries
    ]
    assert found == resume["education"]


def test_the_diploma_only_persona_is_level_2() -> None:
    assert education_of(text_resume(11)).highest_level == 2
