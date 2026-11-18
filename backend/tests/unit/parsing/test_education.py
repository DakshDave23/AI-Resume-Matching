import pytest

from app.models.enums import DegreeLevel
from app.services.parsing.education import EducationEntry, find_degrees, parse_education

D, M, B, DIP, HS = (
    DegreeLevel.DOCTORATE,
    DegreeLevel.MASTER,
    DegreeLevel.BACHELOR,
    DegreeLevel.DIPLOMA,
    DegreeLevel.HIGH_SCHOOL,
)


def entries(text: str) -> list[EducationEntry]:
    return list(parse_education(text).entries)


# --- Degree patterns and levels ---------------------------------------------------


@pytest.mark.parametrize(
    ("text", "degree", "level"),
    [
        ("PhD in Machine Learning", "PhD", D),
        ("Ph.D. in Physics", "Ph.D.", D),
        ("Doctor of Philosophy", "Doctor of Philosophy", D),
        ("M.Tech in Computer Science", "M.Tech", M),
        ("M.Sc Statistics", "M.Sc", M),
        ("MBA, Finance", "MBA", M),
        ("MCA", "MCA", M),
        ("MS in Data Science", "MS", M),
        ("Master's degree in Data Science", "Master's degree", M),
        ("Master’s in Finance", "Master’s", M),  # curly apostrophe
        ("Master of Computer Applications", "Master of Computer Applications", M),
        ("Post Graduate Diploma in Management", "Post Graduate Diploma", M),
        ("PGDM", "PGDM", M),
        ("B.Tech in Computer Science", "B.Tech", B),
        ("B. Tech, Mechanical", "B. Tech", B),
        ("B.E. in Computer Engineering", "B.E.", B),
        ("BE in Mechanical Engineering", "BE", B),
        ("BSc Mathematics", "BSc", B),
        ("B.Com", "B.Com", B),
        ("BCA in Computer Applications", "BCA", B),
        ("Bachelor of Technology", "Bachelor of Technology", B),
        ("Bachelor's in Economics", "Bachelor's", B),
        ("Diploma in Computer Engineering", "Diploma", DIP),
        ("Associate Degree in Nursing", "Associate Degree", DIP),
        ("HSC", "HSC", HS),
        ("Class XII, CBSE", "Class XII", HS),
        ("High School Diploma", "High School Diploma", HS),  # one degree, not two
    ],
)
def test_degree_levels(text: str, degree: str, level: DegreeLevel) -> None:
    (found,) = find_degrees(text)
    assert (found.text, found.level) == (degree, level)


@pytest.mark.parametrize(
    "text",
    [
        "Advanced MS Excel and MS Office",  # Microsoft, not a master's
        "ms in data science",  # two-letter forms only count in capitals
        "Be a team player",
        "Polytechnic graduate",  # a school type, not a degree
        "Embedded systems",
    ],
)
def test_not_degrees(text: str) -> None:
    assert find_degrees(text) == []


# --- Field, institution, year -------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "field"),
    [
        ("B.Tech in Computer Science, Western Institute of Technology, 2017", "Computer Science"),
        ("B.E. in Electronics and Communication, MIT", "Electronics and Communication"),
        ("Bachelor of Technology in Computer Science", "Computer Science"),
        ("Master of Computer Applications, Awadh University", "Computer Applications"),
        ("Bachelor of Science, Deccan University", None),  # "Science" alone names the degree
        ("B.E. (Electronics and Communication)", "Electronics and Communication"),
        ("B.Tech - Information Technology", "Information Technology"),
        ("B.Tech, Indian Institute of Technology Bombay", None),  # a school, not a field
        ("M.Sc in Statistics from Deccan University", "Statistics"),
        ("MBA in Finance 2019", "Finance"),
    ],
)  # fmt: skip
def test_field(line: str, field: str | None) -> None:
    (entry,) = entries(line)
    assert entry.field == field


@pytest.mark.parametrize(
    ("line", "institution"),
    [
        ("B.Tech in CS, Western Institute of Technology, 2017", "Western Institute of Technology"),
        ("M.Sc in Statistics from Deccan University", "Deccan University"),
        ("B.Tech | IIT Delhi | 2016 – 2020", "IIT Delhi"),
        ("High School Diploma, Lincoln High School, 2012", "Lincoln High School"),
        ("BCA, Awadh College (2013-2016)", "Awadh College"),
        ("B.Sc in Physics", None),
    ],
)
def test_institution(line: str, institution: str | None) -> None:
    (entry,) = entries(line)
    assert entry.institution == institution


@pytest.mark.parametrize(
    ("line", "year"),
    [
        ("B.Tech, Western Institute of Technology, 2017", 2017),
        ("B.Tech, IIT Delhi, 2016 – 2020", 2020),  # the graduation year ends the range
        ("M.Tech, Deccan University, expected 2027", 2027),
        ("B.Tech, Deccan University, CGPA 8.75", None),
    ],
)
def test_year(line: str, year: int | None) -> None:
    (entry,) = entries(line)
    assert entry.year == year


# --- Grouping lines into entries ----------------------------------------------------


def test_one_line_per_entry() -> None:
    text = (
        "M.Sc in Statistics, Deccan University, 2020\nB.Sc in Mathematics, Deccan University, 2018"
    )
    assert [(e.degree, e.field, e.year) for e in entries(text)] == [
        ("M.Sc", "Statistics", 2020),
        ("B.Sc", "Mathematics", 2018),
    ]


def test_an_entry_wrapped_over_lines() -> None:
    text = "B.Tech in Computer Science,\nDeccan Institute of Technology,\n2021"
    assert entries(text) == [
        EducationEntry("B.Tech", B, "Computer Science", "Deccan Institute of Technology", 2021)
    ]


def test_institution_above_the_degree() -> None:
    text = """\
Deccan University, Pune            2016 – 2020
Bachelor of Technology in Computer Science
CGPA: 8.5/10
St. Xavier's Junior College, Mumbai     2014 – 2016
HSC (12th), Science"""
    assert entries(text) == [
        EducationEntry("Bachelor of Technology", B, "Computer Science", "Deccan University", 2020),
        EducationEntry("HSC", HS, None, "St. Xavier's Junior College", 2016),
    ]


def test_a_dual_degree_counts_at_its_highest_level() -> None:
    (entry,) = entries("B.Tech + M.Tech (Dual Degree), IIT Bombay, 2019")
    assert (entry.degree, entry.level) == ("M.Tech", M)


def test_stray_lines_are_not_entries() -> None:
    assert entries("Relevant coursework: Data Structures, Operating Systems") == []


def test_highest_level() -> None:
    result = parse_education("M.Sc in Statistics, 2020\nB.Sc in Mathematics, 2018\nHSC, 2015")
    assert result.highest_level == M
    assert parse_education("").highest_level is None
