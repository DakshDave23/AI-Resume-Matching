from datetime import date

import pytest

from app.services.parsing.dates import find_date_ranges
from app.services.parsing.experience import (
    WorkHistory,
    merged_months,
    parse_experience,
    parse_header,
    skill_months,
    stated_months,
)
from app.services.parsing.skills import get_skill_extractor

TODAY = date(2026, 11, 1)


def history(text: str, summary: str = "") -> WorkHistory:
    return parse_experience(text, today=TODAY, summary=summary)


def roles(text: str) -> list[tuple[str | None, str | None, str | None]]:
    return [(r.title, r.company, r.location) for r in history(text).roles]


# --- Interval merging -----------------------------------------------------------


def months_of(*texts: str) -> int:
    return merged_months([find_date_ranges(t, today=TODAY)[0] for t in texts], TODAY)


@pytest.mark.parametrize(
    ("ranges", "expected"),
    [
        (["Jan 2020 – Dec 2020"], 12),
        (["Jan 2020 – Dec 2020", "Jul 2020 – Jun 2021"], 18),  # overlapping
        (["Jan 2020 – Dec 2022", "Mar 2021 – Apr 2021"], 36),  # nested
        (["Jan 2020 – Jun 2020", "Jul 2020 – Dec 2020"], 12),  # back to back
        (["Jan 2020 – Mar 2020", "Jan 2021 – Mar 2021"], 6),  # a gap is not counted, nor penalised
        (["Mar 2020 – Present", "Jan 2022 – Dec 2023", "Jul 2017 – Feb 2020"], 113),  # persona 9
    ],
)
def test_merged_months(ranges: list[str], expected: int) -> None:
    assert months_of(*ranges) == expected


# --- Title, company and location ----------------------------------------------------


@pytest.mark.parametrize(
    ("lines", "expected"),
    [
        (
            ["Senior Engineer | Acme Fintech, Bengaluru"],
            ("Senior Engineer", "Acme Fintech", "Bengaluru"),
        ),
        (["Backend Engineer at Initech Software"], ("Backend Engineer", "Initech Software", None)),
        (
            ["Java Developer", "Contoso Payments, Hyderabad"],
            ("Java Developer", "Contoso Payments", "Hyderabad"),
        ),
        (
            ["Acme Fintech | Senior Engineer"],
            ("Senior Engineer", "Acme Fintech", None),
        ),  # company first
        (["Senior Engineer – Acme Corp"], ("Senior Engineer", "Acme Corp", None)),
        (["Engineer | Acme, Inc., Austin, TX"], ("Engineer", "Acme, Inc.", "Austin, TX")),
        (["Engineer | Acme Pvt Ltd | Pune"], ("Engineer", "Acme Pvt Ltd", "Pune")),
        (["Head of Data Platforms"], ("Head of Data Platforms", None, None)),
        ([], (None, None, None)),
    ],
)
def test_parse_header(lines: list[str], expected: tuple[str | None, ...]) -> None:
    assert parse_header(lines) == expected


# --- Roles in each layout --------------------------------------------------------------


def test_pipe_style_role_on_one_line() -> None:
    text = """\
Senior Engineer | Acme Fintech, Bengaluru | Apr 2021 – Present
- Built payment services.
Engineer | Globex, Pune | Jul 2017 – Mar 2021
- Built claims services."""
    result = history(text)

    assert roles(text) == [
        ("Senior Engineer", "Acme Fintech", "Bengaluru"),
        ("Engineer", "Globex", "Pune"),
    ]
    assert [r.description for r in result.roles] == [
        "- Built payment services.",
        "- Built claims services.",
    ]
    assert result.roles[0].is_current and not result.roles[1].is_current


def test_stacked_header_above_the_date() -> None:
    text = """\
Java Developer
Contoso Payments, Hyderabad
Jun 2022 – Present
- Split a monolith into 8 services, each
with its own database.
Technical Support Engineer
Initrode Telecom, Hyderabad
Jun 2021 – May 2022
- Resolved customer tickets."""
    assert roles(text) == [
        ("Java Developer", "Contoso Payments", "Hyderabad"),
        ("Technical Support Engineer", "Initrode Telecom", "Hyderabad"),
    ]
    # The wrapped line stays in the first role's description; it is not a header.
    assert history(text).roles[0].description.endswith("with its own database.")


def test_date_above_the_title_in_table_templates() -> None:
    text = """\
Sep 2023 – Present
Software Developer | Pinnacle Infotech, Indore
- Build REST APIs.
Jul 2022 – Aug 2023
Associate Developer | Pinnacle Infotech, Indore
- Fixed defects."""
    assert roles(text) == [
        ("Software Developer", "Pinnacle Infotech", "Indore"),
        ("Associate Developer", "Pinnacle Infotech", "Indore"),
    ]
    assert history(text).roles[0].description == "- Build REST APIs."


def test_internships_are_listed_but_not_counted() -> None:
    text = """\
Software Engineer | Umbrella | Dec 2024 – Present
- Build APIs.
Software Engineering Intern | Umbrella | Jun 2024 – Nov 2024
- Fixed bugs."""
    result = history(text)
    assert [r.is_internship for r in result.roles] == [False, True]
    assert result.total_months == 24  # Dec 2024 .. Nov 2026, without the 6 intern months


def test_international_is_not_an_internship() -> None:
    result = history("Engineer | International Bank | 2020 – 2021\n- Built things.")
    assert result.roles[0].is_internship is False


# --- Undated resumes -------------------------------------------------------------------


def test_undated_roles_and_a_stated_total() -> None:
    text = """\
Software Engineer
Wayne Retail Tech, Noida
- Develop inventory services.
Java Developer
Soylent Systems, Lucknow
- Built order modules."""
    result = history(text, summary="Backend developer with 7 years of experience in Java.")

    assert roles(text) == [
        ("Software Engineer", "Wayne Retail Tech", "Noida"),
        ("Java Developer", "Soylent Systems", "Lucknow"),
    ]
    assert all(r.dates is None for r in result.roles)
    assert (result.total_months, result.source) == (84, "summary_statement")
    assert result.current_title == "Software Engineer"  # newest first


@pytest.mark.parametrize(
    ("summary", "months"),
    [
        ("Backend developer with 7 years of experience.", 84),
        ("Over 6+ years of professional software experience.", 72),
        ("4.5 yrs of hands-on exp building APIs", 54),
        ("Engineer with an experience of 3 years in testing.", 36),
        ("Built systems for 5 years.", None),  # no "experience"
        ("", None),
    ],
)
def test_stated_months(summary: str, months: int | None) -> None:
    assert stated_months(summary) == months


def test_no_roles_no_total() -> None:
    result = history("Worked on many interesting projects across the company.")
    assert (result.roles, result.total_months, result.source) == ((), None, None)


# --- Current title ----------------------------------------------------------------------


def test_current_title_is_the_current_role_even_if_listed_second() -> None:
    text = """\
Consultant | Self-employed | Jan 2022 – Dec 2023
- Freelance work.
Senior Developer | Contoso | Mar 2020 – Present
- Bank services."""
    assert history(text).current_title == "Senior Developer"


def test_current_title_without_a_current_role_is_the_latest_end() -> None:
    text = """\
Developer | Globex | Jul 2017 – Feb 2020
- Loans.
Senior Developer | Contoso | Mar 2020 – Jun 2024
- Accounts."""
    assert history(text).current_title == "Senior Developer"


# --- Years per skill -----------------------------------------------------------------


def test_skill_months_merge_overlapping_roles_and_skip_internships() -> None:
    text = """\
Senior Java Developer | Contoso | Mar 2020 – Present
- Spring Boot microservices.
Freelance Consultant | Self-employed | Jan 2022 – Dec 2023
- Java and Spring Boot APIs.
Java Developer | Globex | Jul 2017 – Feb 2020
- Maintained services.
Python Intern | Initech | Jan 2017 – Jun 2017
- Scripts."""
    result = history(text)
    months = skill_months(result, get_skill_extractor(), today=TODAY)

    # Java: all three paid roles, merged, so never more than the total.
    assert months["Java"] == result.total_months == 113
    assert months["Spring Boot"] == 81  # Mar 2020 .. Nov 2026; the freelance years overlap
    assert "Python" not in months  # only in the internship
