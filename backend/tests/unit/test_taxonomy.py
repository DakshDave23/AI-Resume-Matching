import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.models.enums import SkillCategory
from app.services.nlp.taxonomy import (
    Taxonomy,
    TaxonomySkill,
    get_taxonomy,
    load_taxonomy,
    normalize_term,
)

# --- The bundled taxonomy ---------------------------------------------------


def test_bundled_taxonomy_is_valid_and_sized_as_designed() -> None:
    taxonomy = get_taxonomy()

    assert 400 <= len(taxonomy.skills) <= 600  # design doc §5.2
    assert {s.category for s in taxonomy.skills} == set(SkillCategory)


@pytest.mark.parametrize(
    ("term", "skill"),
    [
        # Examples straight from design doc §5.2 and §10 persona 2.
        ("js", "JavaScript"),
        ("es6", "JavaScript"),
        ("k8s", "Kubernetes"),
        ("postgres", "PostgreSQL"),
        ("psql", "PostgreSQL"),
        ("postgre sql", "PostgreSQL"),
        ("springboot", "Spring Boot"),
        ("spring-boot", "Spring Boot"),
        ("ml", "Machine Learning"),
        ("rest", "REST APIs"),
        ("restful services", "REST APIs"),
        ("node js", "Node.js"),
    ],
)
def test_aliases_from_the_design_doc_resolve(term: str, skill: str) -> None:
    assert get_taxonomy().term_index()[term].name == skill


@pytest.mark.parametrize(
    ("a", "b"),
    [("java", "javascript"), ("c", "c#"), ("react", "react native")],
)
def test_never_equivalent_pairs_are_separate_skills(a: str, b: str) -> None:
    index = get_taxonomy().term_index()

    assert index[a] is not index[b]


@pytest.mark.parametrize(
    ("a", "b"),
    [("mysql", "postgresql"), ("rabbitmq", "kafka")],  # worked example §6.6, tier 3
)
def test_related_skills_in_the_worked_example_share_a_category(a: str, b: str) -> None:
    index = get_taxonomy().term_index()

    assert index[a].category == index[b].category


# --- Validation rules -------------------------------------------------------


def make_taxonomy(*skills: dict[str, Any]) -> Taxonomy:
    return Taxonomy.model_validate({"version": "test", "skills": list(skills)})


def test_normalize_term_folds_case_unicode_and_spaces() -> None:
    assert normalize_term("  Node\u00a0 JS ") == "node js"
    assert normalize_term("ﬁnance") == "finance"  # NFKC expands the "fi" ligature


def test_aliases_are_normalized_deduplicated_and_never_repeat_the_name() -> None:
    skill = TaxonomySkill.model_validate(
        {"name": "Kubernetes", "category": "devops", "aliases": [" K8S ", "k8s", "KUBERNETES", ""]}
    )

    assert skill.aliases == ("k8s",)
    assert skill.terms == ("kubernetes", "k8s")


def test_duplicate_names_are_rejected_ignoring_case() -> None:
    with pytest.raises(ValidationError, match="'java' is claimed by Java and JAVA"):
        make_taxonomy(
            {"name": "Java", "category": "language"},
            {"name": "JAVA", "category": "language"},
        )


def test_an_alias_claimed_by_two_skills_is_rejected() -> None:
    with pytest.raises(ValidationError, match="'spark' is claimed by Apache Spark and PySpark"):
        make_taxonomy(
            {"name": "Apache Spark", "category": "data", "aliases": ["spark"]},
            {"name": "PySpark", "category": "data", "aliases": ["spark"]},
        )


def test_an_alias_equal_to_another_skills_name_is_rejected() -> None:
    with pytest.raises(
        ValidationError, match="'react native' is claimed by React and React Native"
    ):
        make_taxonomy(
            {"name": "React", "category": "framework", "aliases": ["react native"]},
            {"name": "React Native", "category": "framework"},
        )


def test_all_clashes_are_reported_at_once() -> None:
    with pytest.raises(ValidationError, match="2 ambiguous term"):
        make_taxonomy(
            {"name": "A", "category": "tool", "aliases": ["x", "y"]},
            {"name": "B", "category": "tool", "aliases": ["x", "y"]},
        )


@pytest.mark.parametrize(
    "skill",
    [
        {"name": "Java", "category": "languages"},  # unknown category
        {"name": "  ", "category": "language"},  # blank name
        {"name": "Java", "category": "language", "colour": "red"},  # unknown field
    ],
    ids=["unknown-category", "blank-name", "unknown-field"],
)
def test_malformed_entries_are_rejected(skill: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        make_taxonomy(skill)


def test_load_taxonomy_reads_a_file(tmp_path: Path) -> None:
    path = tmp_path / "taxonomy.json"
    path.write_text(
        json.dumps({"version": "9", "skills": [{"name": "Go", "category": "language"}]}),
        encoding="utf-8",
    )

    assert load_taxonomy(path).skills[0].name == "Go"
