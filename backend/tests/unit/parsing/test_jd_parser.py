import pytest

from app.models.enums import DegreeLevel, RequirementCategory, Seniority
from app.services.parsing.jd_parser import JobParse, find_education, find_years, parse_job


def kinds(job: JobParse) -> dict[str, str]:
    return {s.name: s.requirement_type.value for s in job.skills}


def requirements(*bullets: str, header: str = "Requirements") -> JobParse:
    return parse_job(header + "\n" + "\n".join(f"- {b}" for b in bullets))


# --- Title, company, seniority ----------------------------------------------------------


def test_labels() -> None:
    job = parse_job(
        "Job Title: Sr. Java Developer\nCompany: Initech\nLocation: Pune\n\nRequirements\n- Java"
    )
    assert (job.title, job.company, job.location) == ("Sr. Java Developer", "Initech", "Pune")
    assert job.seniority == Seniority.SENIOR


def test_title_without_a_label_is_the_first_short_line() -> None:
    job = parse_job("Lead Data Engineer\n\nWe are hiring.\n\nRequirements\n- Python")
    assert (job.title, job.seniority) == ("Lead Data Engineer", Seniority.LEAD)


def test_no_title_when_the_jd_opens_with_prose() -> None:
    assert parse_job("We are hiring a backend engineer to join us.\n").title is None


@pytest.mark.parametrize(
    ("title", "level"),
    [
        ("Principal Engineer", Seniority.PRINCIPAL),
        ("Staff Software Engineer", Seniority.LEAD),
        ("Team Lead - Payments", Seniority.LEAD),
        ("Senior Backend Developer", Seniority.SENIOR),
        ("Junior QA Engineer", Seniority.JUNIOR),
        ("Graduate Trainee", Seniority.JUNIOR),
        ("Data Scientist", Seniority.MID),  # no word for it: mid level
    ],
)
def test_seniority(title: str, level: Seniority) -> None:
    assert parse_job(f"Job Title: {title}\n").seniority == level


# --- Required or preferred --------------------------------------------------------------


def test_the_section_decides_first() -> None:
    job = parse_job(
        "Requirements\n- Experience with Java\n\nNice to have\n- Experience with Docker"
    )
    assert kinds(job) == {"Java": "required", "Docker": "preferred"}


@pytest.mark.parametrize(
    "bullet",
    [
        "Exposure to AWS is a plus",
        "Familiarity with Kafka",
        "Knowledge of Tableau is a bonus",
        "Docker preferred",
        "Docker experience is not required",  # not "required"
        "Strong communication skills are a plus",  # "a plus" outranks "strong"
        "Experience with Kubernetes is nice to have",
    ],
)
def test_preferred_cues_override_a_requirements_section(bullet: str) -> None:
    assert set(kinds(requirements(bullet)).values()) == {"preferred"}


@pytest.mark.parametrize(
    "bullet",
    ["Familiarity with Docker is required", "Must know Docker", "Docker is mandatory"],
)
def test_required_cues_override_a_nice_to_have_section(bullet: str) -> None:
    assert kinds(requirements(bullet, header="Nice to have")) == {"Docker": "required"}


def test_strong_does_not_promote_a_nice_to_have() -> None:
    job = requirements("Strong knowledge of Kubernetes", header="Nice to have")
    assert kinds(job) == {"Kubernetes": "preferred"}


def test_the_nearest_cue_wins_in_a_mixed_sentence() -> None:
    job = requirements("Java is required and Kotlin is a plus")
    assert kinds(job) == {"Java": "required", "Kotlin": "preferred"}


def test_clauses_split_on_semicolons() -> None:
    job = requirements("Strong Java skills; Kotlin preferred")
    assert kinds(job) == {"Java": "required", "Kotlin": "preferred"}


def test_responsibilities_without_cues_are_required() -> None:
    job = requirements("Build REST APIs in Java", header="Responsibilities")
    assert kinds(job) == {"REST APIs": "required", "Java": "required"}


def test_the_strongest_mention_wins() -> None:
    job = parse_job(
        "Responsibilities\n- Deploy services with Docker\n\nNice to have\n- Experience with Docker"
    )
    assert kinds(job) == {"Docker": "preferred"}  # listed as nice to have on purpose


def test_a_jd_without_headers_is_read_whole() -> None:
    job = parse_job(
        "Backend Engineer\nWe need a Python developer with 5+ years of experience. "
        "Django is a plus."
    )
    assert job.title == "Backend Engineer"
    assert kinds(job) == {"Python": "required", "Django": "preferred"}
    assert job.min_experience_years == 5


def test_a_skill_list_line_reports_unmapped_items() -> None:
    job = requirements("Tech stack: Java, Kotlin, Gradle, Frobnicator")
    assert kinds(job) == {"Java": "required", "Kotlin": "required", "Gradle": "required"}
    assert job.unmapped == ("Frobnicator",)


def test_a_wrapped_bullet_is_one_requirement() -> None:
    job = parse_job(
        "Requirements\n- Strong Java skills, with experience building\nmicroservices on AWS"
    )
    assert [r.text for r in job.requirements] == [
        "Strong Java skills, with experience building microservices on AWS"
    ]
    assert set(kinds(job)) == {"Java", "Microservices", "AWS"}


# --- Years ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "years"),
    [
        ("5+ years of experience", (5, None)),
        ("3–5 years of experience", (3, 5)),
        ("3-5 yrs", (3, 5)),
        ("3 to 5 years", (3, 5)),
        ("minimum of 4 years", (4, None)),
        ("Minimum 4 years", (4, None)),
        ("at least 2 yrs", (2, None)),
        ("more than 6 years", (6, None)),
        ("4 or more years", (4, None)),
        ("7 years and above", (7, None)),
        ("five years of experience", (5, None)),
        ("2.5 years", (2.5, None)),
    ],
)
def test_years_patterns(text: str, years: tuple[float, float | None]) -> None:
    (phrase,) = find_years(text)
    assert (phrase.min_years, phrase.max_years) == years


@pytest.mark.parametrize("text", ["a 10 year old company", "founded 20 years ago", "5-3 years"])
def test_not_experience_years(text: str) -> None:
    assert find_years(text) == []


def test_general_years_set_the_minimum() -> None:
    job = requirements("3–5 years of experience in backend development")
    assert (job.min_experience_years, job.max_experience_years) == (3, 5)


def test_the_largest_general_figure_wins() -> None:
    job = requirements("Minimum of 4 years in backend roles", "6+ years of overall experience")
    assert job.min_experience_years == 6


def test_years_of_a_skill_are_its_min_years() -> None:
    job = requirements(
        "4+ years of hands-on experience with Java and Spring Boot",
        "6+ years of overall experience",
    )
    assert {s.name: s.min_years for s in job.skills} == {"Java": 4, "Spring Boot": 4}
    assert job.min_experience_years == 6


def test_years_after_the_skill() -> None:
    job = requirements("Java (5+ years), Spring Boot")
    assert {s.name: s.min_years for s in job.skills} == {"Java": 5, "Spring Boot": None}


def test_a_role_name_is_general_experience() -> None:
    job = requirements("3+ years of experience as a data scientist or machine learning engineer")
    assert job.min_experience_years == 3
    assert all(s.min_years is None for s in job.skills)


def test_skill_years_alone_still_set_the_minimum() -> None:
    assert requirements("5+ years of Java").min_experience_years == 5


def test_preferred_years_are_not_the_minimum() -> None:
    job = requirements("3+ years of experience", "5+ years of experience is a plus")
    assert job.min_experience_years == 3


# --- Education --------------------------------------------------------------------------


def test_degree_and_fields() -> None:
    job = requirements(
        "Master's degree in Statistics, Computer Science, Mathematics or a related field"
    )
    assert job.degree_level == DegreeLevel.MASTER
    assert job.fields_of_study == ("Statistics", "Computer Science", "Mathematics")
    assert job.skills == ()  # field names are not skill claims


def test_the_lowest_accepted_degree_is_required() -> None:
    job = requirements("BS/MS in CS or a related field")
    assert (job.degree_level, job.fields_of_study) == (DegreeLevel.BACHELOR, ("Computer Science",))


def test_a_preferred_degree_is_not_required() -> None:
    job = requirements("Bachelor's degree required; Master's preferred")
    assert (job.degree_level, job.preferred_degree_level) == (
        DegreeLevel.BACHELOR,
        DegreeLevel.MASTER,
    )


def test_a_bare_degree_is_a_bachelors() -> None:
    job = requirements("Degree in Computer Science or a related discipline")
    assert (job.degree_level, job.fields_of_study) == (DegreeLevel.BACHELOR, ("Computer Science",))


@pytest.mark.parametrize(
    ("bullet", "equivalent"),
    [
        ("Bachelor's degree in Computer Science or equivalent experience", True),
        ("Bachelor's degree or equivalent practical experience", True),
        ("Bachelor's degree in Computer Science or a related field", False),
    ],
)
def test_or_equivalent_experience(bullet: str, equivalent: bool) -> None:
    assert requirements(bullet).accepts_equivalent_experience is equivalent


@pytest.mark.parametrize(
    "text",
    [
        "Work closely with the BA team",
        "Intermediate SQL",
        "Partner with the Scrum Master",
        "Take a level of ownership",
        "Advanced MS Excel",
    ],
)
def test_degree_words_that_are_not_degrees(text: str) -> None:
    assert find_education(text) == []


def test_two_letter_degrees_count_beside_education_words() -> None:
    assert [d.level for d in find_education("BS in Physics")] == [DegreeLevel.BACHELOR]


# --- Requirement rows -------------------------------------------------------------------


def test_requirement_categories_and_types() -> None:
    job = parse_job(
        "Responsibilities\n- Build REST APIs\n\n"
        "Requirements\n- 4+ years of experience\n- Strong Java\n"
        "- Bachelor's degree in Computer Science\n- Good communication with the team\n\n"
        "Nice to have\n- Experience with Docker\n\n"
        "Benefits\n- Health insurance"
    )
    assert [(r.category, r.requirement_type.value) for r in job.requirements] == [
        (RequirementCategory.RESPONSIBILITY, "required"),
        (RequirementCategory.EXPERIENCE, "required"),
        (RequirementCategory.SKILL, "required"),
        (RequirementCategory.EDUCATION, "required"),
        (RequirementCategory.SKILL, "required"),  # Communication is a taxonomy skill
        (RequirementCategory.SKILL, "preferred"),
    ]  # benefits are not requirements


def test_a_bullet_with_nothing_we_know_is_other() -> None:
    (row,) = requirements("Willing to travel twice a year").requirements
    assert row.category == RequirementCategory.OTHER


def test_prose_is_split_into_sentences() -> None:
    job = parse_job("Requirements\nYou know Java well. You have used Kafka, e.g. for events.")
    assert [r.text for r in job.requirements] == [
        "You know Java well.",
        "You have used Kafka, e.g. for events.",
    ]


def test_about_and_benefits_are_not_scanned_for_skills() -> None:
    job = parse_job(
        "About us\nWe are a Python shop.\n\nRequirements\n- Java\n\nWhat we offer\n- AWS credits"
    )
    assert kinds(job) == {"Java": "required"}
