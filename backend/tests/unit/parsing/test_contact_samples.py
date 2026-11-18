"""Step 10's "done when": name and email right on every text sample.

Phone, location and profile links are checked against sample_data/ground_truth.json too.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from app.services.extraction import extract_text
from app.services.parsing.contact import ContactInfo, extract_contact
from app.services.parsing.sections import CONTACT, segment

SAMPLES = Path(__file__).resolve().parents[4] / "sample_data"
RESUMES = [
    r
    for r in json.loads((SAMPLES / "ground_truth.json").read_text(encoding="utf-8"))["resumes"]
    if r["expected_parse_status"] == "parsed"
]


def contact_of(resume: dict[str, Any]) -> ContactInfo:
    text = extract_text((SAMPLES / resume["file"]).read_bytes(), resume["format"]).text
    # Sample phones all carry a country code; "IN" is the app's default region.
    return extract_contact(segment(text).text_of(CONTACT), text, region="IN")


def without_scheme(url: str | None) -> str | None:
    return url.removeprefix("https://") if url else None


@pytest.mark.parametrize("resume", RESUMES, ids=lambda r: r["file"])
def test_name_and_email(resume: dict[str, Any]) -> None:
    contact = contact_of(resume)
    assert contact.name == resume["name"]
    assert contact.email == resume["email"]


@pytest.mark.parametrize("resume", RESUMES, ids=lambda r: r["file"])
def test_phone_location_and_links(resume: dict[str, Any]) -> None:
    contact = contact_of(resume)
    assert contact.phone == resume["phone_e164"]
    assert contact.location == resume["location"]
    assert without_scheme(contact.linkedin_url) == resume["linkedin"]
    assert without_scheme(contact.github_url) == resume["github"]
