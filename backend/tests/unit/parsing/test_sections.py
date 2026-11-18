import pytest

from app.services.parsing.sections import (
    RESUME_HEADER_DICTIONARY,
    RESUME_HEADERS,
    HeaderDictionary,
    normalize_header,
    segment,
)


def names(text: str) -> list[str]:
    return [s.name for s in segment(text).sections]


# --- What counts as a header --------------------------------------------------


@pytest.mark.parametrize(
    ("line", "section"),
    [
        ("Work Experience", "experience"),
        ("WORK EXPERIENCE", "experience"),
        ("Professional Experience:", "experience"),
        ("CAREER HISTORY:", "experience"),
        ("Employment History", "experience"),
        ("Tech Stack", "skills"),
        ("Core Competencies", "skills"),
        ("Technical Skills", "skills"),
        ("Academic Qualifications", "education"),
        ("About Me", "summary"),
        ("Profile", "summary"),
        ("Key Projects", "projects"),
        ("Licenses & Certifications", "certifications"),
        ("Hobbies", "other"),
        ("  Education  ", "education"),  # stray spaces
        ("Work Experiance", "experience"),  # typo: fuzzy match
        ("Technical Skill", "skills"),
    ],
)
def test_recognises_header_variants(line: str, section: str) -> None:
    found = RESUME_HEADER_DICTIONARY.match(line)
    assert found is not None
    assert found.section == section


@pytest.mark.parametrize(
    "line",
    [
        "- Skills",  # a bullet
        "experience",  # lower case: the tail of a wrapped sentence
        "Java Developer",
        "Software Developer | Pinnacle Infotech, Indore",
        "Languages: Java, Python",  # a skill group line, not a header
        "Education: B.Tech, 2020",
        "Summary of my experience in backend engineering roles",  # too long
        "Education.",
        "Experience 2019",
        "Skillsoft",  # a company that only looks like "skills"
        "",
    ],
)
def test_rejects_lines_that_are_not_headers(line: str) -> None:
    assert RESUME_HEADER_DICTIONARY.match(line) is None


def test_all_caps_or_a_colon_lowers_the_bar_for_a_fuzzy_match() -> None:
    # "projetcs" vs "projects" scores 87.5: below the plain bar (90), above the cue bar (85).
    assert RESUME_HEADER_DICTIONARY.match("Projetcs") is None
    assert RESUME_HEADER_DICTIONARY.match("PROJETCS") is not None
    assert RESUME_HEADER_DICTIONARY.match("Projetcs:") is not None


def test_normalize_header() -> None:
    assert normalize_header("  Licenses & Certifications: ") == "licenses and certifications"
    assert normalize_header("SKILLS / TOOLS") == "skills tools"


def test_every_dictionary_variant_matches_its_own_section() -> None:
    for section, variants in RESUME_HEADERS.items():
        for variant in variants:
            found = RESUME_HEADER_DICTIONARY.match(variant.title())
            assert found is not None, variant
            assert found.section == section, variant
            assert len(variant.split()) <= 5, variant


def test_a_variant_listed_under_two_sections_is_rejected() -> None:
    with pytest.raises(ValueError, match="both"):
        HeaderDictionary({"skills": ["skills"], "other": ["Skills"]})


# --- Splitting ------------------------------------------------------------------

RESUME = """\
Asha Rao
asha.rao@example.com | +1 202 555 0100

SUMMARY:
Backend developer with 5 years of experience.

EXPERIENCE:
Software Engineer | Acme, Pune
Jan 2020 – Present
- Built Spring Boot services.

SKILLS:
Java, Spring Boot, SQL

EDUCATION:
B.E. in Computer Engineering, Pune College of Engineering, 2019
"""


def test_splits_upper_case_colon_headers() -> None:
    result = segment(RESUME)

    assert result.names() == ["contact", "summary", "experience", "skills", "education"]
    assert result.text_of("contact").startswith("Asha Rao\n")
    assert result.text_of("skills") == "Java, Spring Boot, SQL"
    assert result.text_of("experience") == (
        "Software Engineer | Acme, Pune\nJan 2020 – Present\n- Built Spring Boot services."
    )
    assert [s.header for s in result.sections][1:] == [
        "SUMMARY:",
        "EXPERIENCE:",
        "SKILLS:",
        "EDUCATION:",
    ]


def test_text_before_the_first_header_is_the_contact_block() -> None:
    assert segment("Asha Rao\nasha@example.com\nSkills\nJava").text_of("contact") == (
        "Asha Rao\nasha@example.com"
    )


def test_no_headers_means_everything_is_contact() -> None:
    result = segment("Asha Rao\nJava developer.\nBuilt things.")
    assert result.names() == ["contact"]


def test_a_resume_that_starts_with_a_header_has_no_contact_section() -> None:
    assert names("Summary\nBackend developer.") == ["summary"]


def test_an_empty_section_is_kept() -> None:
    result = segment("Projects\nSkills\nJava")
    assert result.names() == ["projects", "skills"]
    assert result.text_of("projects") == ""


def test_an_unparsed_section_stops_the_one_above_it() -> None:
    result = segment("Skills\nJava, SQL\nHobbies\nChess, cricket")
    assert result.text_of("skills") == "Java, SQL"
    assert result.text_of("other") == "Chess, cricket"


def test_a_repeated_section_is_merged() -> None:
    # A two-column page can split one section, or a resume can repeat a header on page 2.
    result = segment("Experience\nRole A\nSkills\nJava\nExperience\nRole B")
    assert result.text_of("experience") == "Role A\n\nRole B"
    assert result.as_dict() == {"experience": "Role A\n\nRole B", "skills": "Java"}


def test_a_line_continuing_a_wrapped_sentence_is_not_a_header() -> None:
    text = "Summary\nBackend developer with deep knowledge of\nEducation\ntechnology."
    assert names(text) == ["summary"]


def test_header_after_a_finished_line_still_counts() -> None:
    assert names("Summary\nBackend developer.\nEducation\nB.Tech, 2019") == [
        "summary",
        "education",
    ]
    assert names("Summary\nLed Team A\nSkills\nJava") == ["summary", "skills"]


def test_inner_blank_lines_are_kept_and_outer_ones_trimmed() -> None:
    result = segment("Experience\n\nRole A\n- did x\n\nRole B\n\n\nSkills\nJava")
    assert result.text_of("experience") == "Role A\n- did x\n\nRole B"
