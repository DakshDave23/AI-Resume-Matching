"""Step 14's "done when": the Java JD's extraction matches expectations.

All three sample JDs are checked against sample_data/jds/expected.yaml, as copied
into ground_truth.json: title, seniority, required and preferred skills, years,
degree level, fields and the "or equivalent experience" flag.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from app.services.parsing.jd_parser import JobParse, parse_job

SAMPLES = Path(__file__).resolve().parents[4] / "sample_data"
JDS = json.loads((SAMPLES / "ground_truth.json").read_text(encoding="utf-8"))["jds"]


def parsed(jd: dict[str, Any]) -> JobParse:
    return parse_job((SAMPLES / jd["file"]).read_text(encoding="utf-8"))


def java_jd() -> JobParse:
    return parsed(next(j for j in JDS if j["id"] == "backend_java"))


@pytest.mark.parametrize("jd", JDS, ids=lambda j: j["id"])
def test_extraction_matches_expectations(jd: dict[str, Any]) -> None:
    job = parsed(jd)
    found = {
        "title": job.title,
        "seniority": job.seniority.value,
        "required_skills": sorted(job.required_skills),
        "preferred_skills": sorted(job.preferred_skills),
        "min_experience_years": job.min_experience_years,
        "max_experience_years": job.max_experience_years,
        "degree_level": job.degree_level,
        "fields_of_study": list(job.fields_of_study),
        "accepts_equivalent_experience": job.accepts_equivalent_experience,
    }
    expected = {key: jd[key] for key in found}
    expected["required_skills"] = sorted(expected["required_skills"])
    expected["preferred_skills"] = sorted(expected["preferred_skills"])
    assert found == expected
    assert job.unmapped == ()


def test_java_jd_requirement_rows() -> None:
    job = java_jd()
    rows = [(r.category.value, r.requirement_type.value) for r in job.requirements]
    assert rows == (
        [("responsibility", "required")] * 7
        + [("experience", "required")]
        + [("skill", "required")] * 4
        + [("education", "required")]
        + [("skill", "preferred")] * 3
    )
    assert job.requirements[8].text == "Strong proficiency in Java and Spring Boot."
    assert job.company == "Northwind Payments (synthetic)"


def test_every_skill_keeps_the_bullet_it_came_from() -> None:
    kafka = next(s for s in java_jd().skills if s.name == "Kafka")
    assert kafka.source_text == "Familiarity with Kafka or other event streaming platforms."
    assert kafka.default_weight == 0.5
