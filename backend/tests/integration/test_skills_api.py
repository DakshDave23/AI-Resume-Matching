"""GET /skills: the chip editor's autocomplete."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import SkillCategory
from app.repositories.skills import add_custom_skill
from tests.fakes import FakeEncoder

pytestmark = pytest.mark.integration


def names(api: TestClient, q: str, **params: str | int) -> list[str]:
    response = api.get("/api/v1/skills", params={"q": q, **params})
    assert response.status_code == 200, response.text
    return [s["name"] for s in response.json()]


def test_exact_name_first_then_names_starting_with_the_text(api: TestClient) -> None:
    found = names(api, "java")
    assert found[0] == "Java"
    assert found.index("Java EE") < found.index("JavaScript")  # shorter names first


def test_an_alias_finds_its_skill(api: TestClient) -> None:
    assert names(api, "k8s")[0] == "Kubernetes"
    assert names(api, "postgres")[0] == "PostgreSQL"


def test_case_and_spaces_do_not_matter(api: TestClient) -> None:
    assert names(api, "  SPRING boot ")[0] == "Spring Boot"


def test_wildcards_are_plain_characters(api: TestClient) -> None:
    assert names(api, "%") == []
    assert names(api, "_") == []


def test_limit(api: TestClient) -> None:
    assert len(names(api, "a", limit=3)) == 3


def test_custom_skills_are_included(api: TestClient, seeded_session: Session) -> None:
    add_custom_skill(seeded_session, "Zz Quantum Widgets", SkillCategory.TOOL, FakeEncoder())
    seeded_session.commit()
    response = api.get("/api/v1/skills", params={"q": "quantum wid"})
    assert response.json() == [
        {"id": response.json()[0]["id"], "name": "Zz Quantum Widgets", "category": "tool",
         "is_custom": True},
    ]  # fmt: skip


@pytest.mark.parametrize("params", [{}, {"q": ""}, {"q": "x" * 101}, {"q": "java", "limit": 0}])
def test_bad_queries_are_422(api: TestClient, params: dict[str, str | int]) -> None:
    assert api.get("/api/v1/skills", params=params).status_code == 422
