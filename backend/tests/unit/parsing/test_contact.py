import pytest

from app.services.parsing.contact import (
    extract_contact,
    find_email,
    find_github,
    find_linkedin,
    find_location,
    find_name,
    find_phone,
    looks_like_name,
)

BLOCK = """\
Asha Rao
Backend Engineer
asha.rao@example.com | +91 98765 43210 | Pune, India
linkedin.com/in/asha-rao-example | github.com/asharao-example"""


def test_extracts_every_field_from_a_typical_contact_block() -> None:
    contact = extract_contact(BLOCK, BLOCK, region="IN")

    assert contact.name == "Asha Rao"
    assert contact.email == "asha.rao@example.com"
    assert contact.phone == "+919876543210"
    assert contact.location == "Pune, India"
    assert contact.linkedin_url == "https://linkedin.com/in/asha-rao-example"
    assert contact.github_url == "https://github.com/asharao-example"


def test_missing_fields_are_none() -> None:
    contact = extract_contact("Asha Rao", "Asha Rao\nSkills\nJava", region="IN")
    assert contact.name == "Asha Rao"
    assert (contact.email, contact.phone, contact.location) == (None, None, None)
    assert (contact.linkedin_url, contact.github_url) == (None, None)


# --- Email ------------------------------------------------------------------


def test_email_falls_back_to_the_full_text() -> None:
    # Some templates put contact details in the page footer, which is read last.
    full = "Asha Rao\nSkills\nJava\nContact me at asha.rao@mail.example.co.in."
    assert find_email("Asha Rao", full) == "asha.rao@mail.example.co.in"


def test_email_prefers_the_contact_block() -> None:
    assert find_email("me@example.com", "ref@example.com\nme@example.com") == "me@example.com"


# --- Phone ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("+1 (303) 555-0177", "+13035550177"),
        ("+1-415-555-0182", "+14155550182"),
        ("+44 20 7946 0321", "+442079460321"),
        ("Phone: 98765 43210", "+919876543210"),  # no country code: default region
        ("Mobile: 098765-43210", "+919876543210"),
    ],
)
def test_phone_is_normalised_to_e164(text: str, expected: str) -> None:
    assert find_phone(text, region="IN") == expected


def test_the_default_region_applies_only_without_a_country_code() -> None:
    assert find_phone("(303) 555-0177", region="US") == "+13035550177"
    assert find_phone("+1 (303) 555-0177", region="GB") == "+13035550177"


@pytest.mark.parametrize("text", ["Jan 2019 – Mar 2021", "2019 - 2021", "ID 12345", "GPA 8.75"])
def test_dates_and_other_numbers_are_not_phones(text: str) -> None:
    assert find_phone(text, region="IN") is None


# --- Links ------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "linkedin.com/in/asha-rao",
        "https://www.linkedin.com/in/asha-rao/",
        "LinkedIn: in.linkedin.com/in/asha-rao",
    ],
)
def test_linkedin_urls_are_normalised(text: str) -> None:
    assert find_linkedin(text) == "https://linkedin.com/in/asha-rao"


@pytest.mark.parametrize(
    "text",
    ["github.com/asha-rao", "https://github.com/asha-rao/", "github.com/asha-rao/payments-api"],
)
def test_github_url_keeps_only_the_profile(text: str) -> None:
    assert find_github(text) == "https://github.com/asha-rao"


# --- Name -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("block", "expected"),
    [
        ("Asha Rao\nBackend Engineer", "Asha Rao"),
        ("ASHA RAO\nBACKEND ENGINEER", "Asha Rao"),
        ("Meera Pillai — Full Stack Developer", "Meera Pillai"),
        ("Asha K. Rao | Pune", "Asha K. Rao"),
        ("Anne-Marie O'Neil", "Anne-Marie O'Neil"),
        ("Anne-Marie O’Neil", "Anne-Marie O’Neil"),  # curly apostrophe
        ("McDonald Rao", None),  # inner capitals only in hyphenated/apostrophe names
        ("Ravi van Dijk", "Ravi van Dijk"),
        ("Senior Software Engineer\nAsha Rao", "Asha Rao"),  # headline first
        ("Curriculum Vitae\nAsha Rao", "Asha Rao"),
        ("Java Developer\nasha@example.com", None),
        ("asha@example.com | +91 98765 43210", None),
        ("Asha", None),  # one word is not enough to be sure
    ],
)
def test_name_is_the_first_name_shaped_piece(block: str, expected: str | None) -> None:
    assert find_name(block, block) == expected


def test_a_name_label_wins() -> None:
    full = "Personal Details\nName: Asha Rao\nDate of Birth: 01/01/1995"
    assert find_name("Software Engineer", full) == "Asha Rao"


@pytest.mark.parametrize(
    "text", ["Pune, India", "Data Scientist", "Asha Rao 2020", "asha rao", "A B C D E"]
)
def test_looks_like_name_rejects(text: str) -> None:
    assert looks_like_name(text) is False


# --- Location ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("block", "expected"),
    [
        ("asha@example.com | +91 98765 43210 | Pune, India", "Pune, India"),
        ("asha@example.com | Austin, TX 78701", "Austin, TX"),
        ("asha@example.com | +91 98765 43210 | Pune", "Pune"),  # lone city on a contact line
        ("Location: Navi Mumbai, Maharashtra", "Navi Mumbai, Maharashtra"),
        ("Asha Rao\nJava Developer", None),  # a headline is not a place
        ("Asha Rao\nBengaluru, Karnataka, India", "Bengaluru, Karnataka, India"),
    ],
)
def test_location(block: str, expected: str | None) -> None:
    assert find_location(block, "Asha Rao") == expected
