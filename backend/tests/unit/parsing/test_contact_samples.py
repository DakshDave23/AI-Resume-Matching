"""Step 10's "done when": name and email right on every text sample.

Phone, location and profile links are checked against sample_data/ground_truth.json too.
"""

import pytest

from app.services.parsing.contact import ContactInfo, extract_contact
from app.services.parsing.sections import CONTACT
from tests.samples import TEXT_RESUMES, Sample, resume_id, resume_sections, resume_text


def contact_of(resume: Sample) -> ContactInfo:
    # Sample phones all carry a country code; "IN" is the app's default region.
    contact_block = resume_sections(resume).text_of(CONTACT)
    return extract_contact(contact_block, resume_text(resume), region="IN")


def without_scheme(url: str | None) -> str | None:
    return url.removeprefix("https://") if url else None


@pytest.mark.parametrize("resume", TEXT_RESUMES, ids=resume_id)
def test_name_and_email(resume: Sample) -> None:
    contact = contact_of(resume)
    assert contact.name == resume["name"]
    assert contact.email == resume["email"]


@pytest.mark.parametrize("resume", TEXT_RESUMES, ids=resume_id)
def test_phone_location_and_links(resume: Sample) -> None:
    contact = contact_of(resume)
    assert contact.phone == resume["phone_e164"]
    assert contact.location == resume["location"]
    assert without_scheme(contact.linkedin_url) == resume["linkedin"]
    assert without_scheme(contact.github_url) == resume["github"]
