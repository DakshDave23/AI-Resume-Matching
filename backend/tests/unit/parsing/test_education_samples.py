"""Step 13's "done when": degree levels right on every text sample.

Each entry's degree, field, institution, year and level, and the resume's
highest level, are checked against sample_data/ground_truth.json.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from app.services.extraction import extract_text
from app.services.parsing.education import EducationResult, parse_education
from app.services.parsing.sections import segment

SAMPLES = Path(__file__).resolve().parents[4] / "sample_data"
RESUMES = [
    r
    for r in json.loads((SAMPLES / "ground_truth.json").read_text(encoding="utf-8"))["resumes"]
    if r["expected_parse_status"] == "parsed"
]


def education_of(resume: dict[str, Any]) -> EducationResult:
    text = extract_text((SAMPLES / resume["file"]).read_bytes(), resume["format"]).text
    return parse_education(segment(text).text_of("education"))


@pytest.mark.parametrize("resume", RESUMES, ids=lambda r: r["file"])
def test_highest_degree_level(resume: dict[str, Any]) -> None:
    assert education_of(resume).highest_level == resume["degree_level"]


@pytest.mark.parametrize("resume", RESUMES, ids=lambda r: r["file"])
def test_entries_match_ground_truth(resume: dict[str, Any]) -> None:
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
    resume = next(r for r in RESUMES if r["id"] == 11)
    assert education_of(resume).highest_level == 2
