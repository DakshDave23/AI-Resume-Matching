"""Step 9's "done when": sections come out right on every text sample.

The expected section list is `sections` in sample_data/ground_truth.json. To check
the boundaries too, the persona YAML each sample was rendered from says which text
belongs where: every summary, bullet, skill, school and certification must land in
its own section, and the long ones in no other.
"""

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.services.extraction import extract_text
from app.services.parsing.sections import CONTACT, Segmentation, segment

SAMPLES = Path(__file__).resolve().parents[4] / "sample_data"
RESUMES = [
    r
    for r in json.loads((SAMPLES / "ground_truth.json").read_text(encoding="utf-8"))["resumes"]
    if r["expected_parse_status"] == "parsed"
]
PERSONAS: dict[int, dict[str, Any]] = {
    p["id"]: p
    for p in (
        yaml.safe_load(f.read_text(encoding="utf-8"))
        for f in sorted((SAMPLES / "personas").glob("*.yaml"))
    )
}


def flat(text: str) -> str:
    """PDF lines wrap where the page ends; compare text with wraps ignored."""
    return " ".join(text.split())


def segment_sample(resume: dict[str, Any]) -> Segmentation:
    path = SAMPLES / resume["file"]
    return segment(extract_text(path.read_bytes(), resume["format"]).text)


def expected_content(persona: dict[str, Any]) -> dict[str, list[str]]:
    """Text that must appear in each section."""
    experience = []
    for role in persona["experience"]:
        experience += [role["title"], role["company"], *role["bullets"]]
    return {
        CONTACT: [persona["contact"]["name"], persona["contact"]["email"]],
        "summary": [persona["summary"]],
        "experience": experience,
        "skills": [item for items in persona["skills"].values() for item in items],
        "education": [e["institution"] for e in persona["education"]],
        "certifications": persona.get("certifications", []),
    }


@pytest.mark.parametrize("resume", RESUMES, ids=lambda r: r["file"])
def test_every_expected_section_is_found_once(resume: dict[str, Any]) -> None:
    result = segment_sample(resume)

    found = [s.name for s in result.sections]
    assert found[0] == CONTACT
    assert sorted(found[1:]) == sorted(resume["sections"])  # no extras, none twice


@pytest.mark.parametrize("resume", RESUMES, ids=lambda r: r["file"])
def test_content_lands_in_the_right_section(resume: dict[str, Any]) -> None:
    result = segment_sample(resume)
    sections = {name: flat(text) for name, text in result.as_dict().items()}

    for name, snippets in expected_content(PERSONAS[resume["id"]]).items():
        for snippet in snippets:
            assert flat(snippet) in sections.get(name, ""), f"{snippet!r} not in {name}"
            # Long text (a summary, a bullet) belongs to one section only. Skills don't:
            # "microservice architecture" is both a skill and a phrase in a bullet.
            if name != "skills" and len(snippet) >= 25:
                elsewhere = [n for n, t in sections.items() if n != name and flat(snippet) in t]
                assert not elsewhere, f"{snippet!r} also in {elsewhere}"


def test_samples_cover_the_header_styles_the_doc_asks_for() -> None:
    """Upper-case headers, headers with colons and a two-column layout (design doc §13)."""
    headers = [
        s.header for r in RESUMES for s in segment_sample(r).sections if s.header is not None
    ]
    assert any(h.isupper() for h in headers)
    assert any(h.endswith(":") for h in headers)
    assert {"Tech Stack", "Career History", "About Me", "Employment History"} <= set(headers)
    assert any(r["layout"] == "two_column" for r in RESUMES)
