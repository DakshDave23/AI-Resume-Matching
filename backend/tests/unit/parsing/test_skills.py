import pytest

from app.models.enums import SkillSource
from app.services.parsing.sections import segment
from app.services.parsing.skills import SkillExtraction, get_skill_extractor

EXPERIENCE = SkillSource.EXPERIENCE


def in_text(text: str) -> list[str]:
    """Skills found in free text (an experience bullet), in order."""
    return [m.skill for m in get_skill_extractor().find_mentions(text, EXPERIENCE)]


def in_list(text: str) -> tuple[list[str], list[str]]:
    """Skills and unmapped items from a skills-section body."""
    mentions, unmapped = get_skill_extractor().scan_skill_list(text)
    return [m.skill for m in mentions], unmapped


def resume(text: str) -> SkillExtraction:
    return get_skill_extractor().extract_resume(segment(text))


# --- Exact and alias pass -------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Built a JavaScript front end", ["JavaScript"]),  # the Java/JavaScript guard
        ("Wrote Java and JavaScript", ["Java", "JavaScript"]),
        ("Services in Spring Boot", ["Spring Boot"]),  # longest match: not also Spring
        ("Reports in T-SQL", ["T-SQL"]),  # not also SQL
        ("Deployed on k8s with Postgres", ["Kubernetes", "PostgreSQL"]),
        ("Used Node.js/Express for the API", ["Node.js", "Express.js"]),  # slash split
        ("C, C++ and C# tooling", ["C", "C++", "C#"]),
        ("Ran CI/CD pipelines", ["CI/CD"]),
    ],
)
def test_exact_and_alias_matches(text: str, expected: list[str]) -> None:
    assert in_text(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Handled tax audits", ["Auditing"]),
        ("Split the monolith into microservices", ["Microservices"]),
        ("Wrote unit tests for every module", ["Unit Testing"]),
    ],
)
def test_simple_plurals_match(text: str, expected: list[str]) -> None:
    assert in_text(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Rewrote the gateway in Go", ["Go"]),
        ("I am the go-to person for releases", []),
        ("Helped the rest of the team", []),
        ("Designed REST endpoints", ["REST APIs"]),
        ("Wrote Express middleware", ["Express.js"]),
        ("Reported to C-level executives", []),
        ("Led R&D for the payments team", []),
        ("Worked in a fast-paced spring release cycle", []),
    ],
)
def test_ambiguous_words_need_the_skill_spelling_in_free_text(
    text: str, expected: list[str]
) -> None:
    assert in_text(text) == expected


def test_ambiguous_words_match_in_any_case_inside_a_skill_list() -> None:
    skills, _ = in_list("go, rest, ruby")
    assert skills == ["Go", "REST APIs", "Ruby"]


# --- Skill lists: fuzzy pass, labels, unmapped ------------------------------------


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        ("Node JS", ["Node.js"]),  # an alias as a whole, not "node" + "JS" (JavaScript)
        ("Postgre SQL", ["PostgreSQL"]),  # an alias, not SQL
        # fuzzy pass
        ("Kubernetis", ["Kubernetes"]),
        ("Spring Bot", ["Spring Boot"]),  # beats the partial exact hit "Spring"
        ("Postgress SQL", ["PostgreSQL"]),  # beats the partial exact hit "SQL"
        ("Type Script", ["TypeScript"]),  # split word: compared without spaces
        ("Java 11", ["Java"]),  # the version doesn't make the item partial
        ("HTML5/CSS3", ["HTML", "CSS"]),
    ],
)
def test_skill_list_items(item: str, expected: list[str]) -> None:
    assert in_list(item) == (expected, [])


def test_fuzzy_hits_are_marked() -> None:
    mentions, _ = get_skill_extractor().scan_skill_list("Java, Postgress SQL")
    assert [(m.skill, m.fuzzy, m.text) for m in mentions] == [
        ("Java", False, "Java"),
        ("PostgreSQL", True, "Postgress SQL"),
    ]


def test_group_labels_are_not_skills() -> None:
    skills, unmapped = in_list("SQL: PostgreSQL, MySQL\n- Cloud: AWS")
    assert skills == ["PostgreSQL", "MySQL", "AWS"]  # no "SQL" from the label
    assert unmapped == []


def test_items_outside_the_taxonomy_are_unmapped() -> None:
    skills, unmapped = in_list("Java, Hystrix, Spring Boot (Actuator), 2019, .NET")
    assert skills == ["Java", "Spring Boot", ".NET"]
    assert unmapped == ["Hystrix"]


def test_a_list_wrapped_after_a_comma_is_one_list() -> None:
    assert in_list("Java, Spring Boot,\nDocker") == (["Java", "Spring Boot", "Docker"], [])


def test_long_sentences_in_a_skills_section_are_not_unmapped_items() -> None:
    skills, unmapped = in_list("Comfortable owning services from design to production in Java")
    assert (skills, unmapped) == (["Java"], [])


# --- A whole resume: sections, provenance, evidence -------------------------------

RESUME = """\
Asha Rao
Backend Engineer
asha.rao@example.com | github.com/asharao-example
Summary
Java developer with 5 years of experience.
Experience
Software Engineer | Acme, Pune
- Built payment services in Java and Spring Boot,
backed by PostgreSQL and Kafka.
Skills
Languages: Java, Python
Tools: Docker, Hystrix
Education
B.E. in Electronics and Communication, Pune College of Engineering, 2019
"""


def test_skills_come_with_sources_counts_and_evidence() -> None:
    result = resume(RESUME)
    java = next(s for s in result.skills if s.name == "Java")

    assert java.sources == (SkillSource.SKILLS_SECTION, SkillSource.EXPERIENCE, SkillSource.SUMMARY)
    assert java.mention_count == 3
    # A bullet is the best evidence; the wrapped second line is joined back on.
    assert java.evidence == (
        "Built payment services in Java and Spring Boot, backed by PostgreSQL and Kafka."
    )
    assert result.unmapped == ("Hystrix",)


def test_skills_only_in_a_list_use_the_list_line_as_evidence() -> None:
    docker = next(s for s in resume(RESUME).skills if s.name == "Docker")
    assert docker.sources == (SkillSource.SKILLS_SECTION,)
    assert docker.evidence == "Tools: Docker, Hystrix"


def test_contact_links_and_degree_names_are_not_skills() -> None:
    names = resume(RESUME).names()
    assert "GitHub" not in names  # github.com/... is a link
    assert "Communication" not in names  # part of the degree name
    assert names == {"Java", "Python", "Spring Boot", "PostgreSQL", "Kafka", "Docker"}


def test_skills_are_sorted_by_name() -> None:
    names = [s.name for s in resume(RESUME).skills]
    assert names == sorted(names, key=str.lower)
