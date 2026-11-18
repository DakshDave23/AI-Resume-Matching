"""Step 9's "done when": sections come out right on every text sample.

The expected section list is `sections` in sample_data/ground_truth.json. To check
the boundaries too, the persona YAML each sample was rendered from says which text
belongs where: every summary, bullet, skill, school and certification must land in
its own section, and the long ones in no other.
"""

from typing import Any

import pytest

from app.services.parsing.sections import CONTACT
from tests.samples import TEXT_RESUMES, Sample, persona, resume_id, resume_sections


def flat(text: str) -> str:
    """PDF lines wrap where the page ends; compare text with wraps ignored."""
    return " ".join(text.split())


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


@pytest.mark.parametrize("resume", TEXT_RESUMES, ids=resume_id)
def test_every_expected_section_is_found_once(resume: Sample) -> None:
    result = resume_sections(resume)

    found = [s.name for s in result.sections]
    assert found[0] == CONTACT
    assert sorted(found[1:]) == sorted(resume["sections"])  # no extras, none twice


@pytest.mark.parametrize("resume", TEXT_RESUMES, ids=resume_id)
def test_content_lands_in_the_right_section(resume: Sample) -> None:
    result = resume_sections(resume)
    sections = {name: flat(text) for name, text in result.as_dict().items()}

    for name, snippets in expected_content(persona(resume["id"])).items():
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
        s.header for r in TEXT_RESUMES for s in resume_sections(r).sections if s.header is not None
    ]
    assert any(h.isupper() for h in headers)
    assert any(h.endswith(":") for h in headers)
    assert {"Tech Stack", "Career History", "About Me", "Employment History"} <= set(headers)
    assert any(r["layout"] == "two_column" for r in TEXT_RESUMES)
