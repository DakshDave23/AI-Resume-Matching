"""Step 11's "done when": skill recall checked against sample_data/ground_truth.json.

Each resume must yield exactly its expected canonical skills (no misses, no
extras) and its expected unmapped skill-list items. The design doc's target is
F1 >= 0.85 across all resumes; the per-resume checks are stricter.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from app.services.extraction import extract_text
from app.services.parsing.sections import segment
from app.services.parsing.skills import SkillExtraction, get_skill_extractor

SAMPLES = Path(__file__).resolve().parents[4] / "sample_data"
RESUMES = [
    r
    for r in json.loads((SAMPLES / "ground_truth.json").read_text(encoding="utf-8"))["resumes"]
    if r["expected_parse_status"] == "parsed"
]


def skills_of(resume: dict[str, Any]) -> SkillExtraction:
    text = extract_text((SAMPLES / resume["file"]).read_bytes(), resume["format"]).text
    return get_skill_extractor().extract_resume(segment(text))


@pytest.mark.parametrize("resume", RESUMES, ids=lambda r: r["file"])
def test_skills_match_ground_truth(resume: dict[str, Any]) -> None:
    result = skills_of(resume)
    expected = set(resume["skills"])

    assert sorted(expected - result.names()) == [], "missed"
    assert sorted(result.names() - expected) == [], "not in the resume"
    assert list(result.unmapped) == resume["unmapped_skill_terms"]


def test_f1_across_all_samples_meets_the_design_target() -> None:
    true_pos = false_pos = false_neg = 0
    for resume in RESUMES:
        found, expected = skills_of(resume).names(), set(resume["skills"])
        true_pos += len(found & expected)
        false_pos += len(found - expected)
        false_neg += len(expected - found)
    precision = true_pos / (true_pos + false_pos)
    recall = true_pos / (true_pos + false_neg)
    assert 2 * precision * recall / (precision + recall) >= 0.85


def test_every_skill_has_evidence_from_the_resume() -> None:
    for resume in RESUMES:
        for skill in skills_of(resume).skills:
            assert skill.evidence, skill.name
            assert skill.mention_count >= 1
            assert skill.sources
