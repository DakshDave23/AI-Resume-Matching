"""Small helpers behind the rankings, export and candidate routes."""

import csv
import io
import uuid
from decimal import Decimal

import pytest

from app.repositories.rankings import RankingRecord
from app.services.rankings import (
    CSV_COLUMNS,
    export_filename,
    missing_required_count,
    rankings_csv,
    top_matched_skills,
    years,
)


def skill(name: str, tier: str) -> dict[str, str]:
    return {"skill": name, "tier": tier}


def test_top_skills_put_full_credit_first_and_keep_five() -> None:
    matched = [
        skill("PostgreSQL", "related"), skill("Java", "exact"), skill("Kafka", "contextual"),
        skill("REST APIs", "alias"), skill("Docker", "exact"), skill("Git", "exact"),
        skill("AWS", "exact"),
    ]  # fmt: skip
    assert top_matched_skills(matched) == ["Java", "REST APIs", "Docker", "Git", "AWS"]
    assert top_matched_skills([]) == []


def test_missing_required_count() -> None:
    missing = [
        {"skill": "AWS", "requirement_type": "preferred"},
        {"skill": "Java", "requirement_type": "required"},
    ]
    assert missing_required_count(missing) == 1


@pytest.mark.parametrize(("months", "shown"), [(54, 4.5), (113, 9.4), (0, 0.0), (None, None)])
def test_years(months: int | None, shown: float | None) -> None:
    assert years(months) == shown


@pytest.mark.parametrize(
    ("title", "filename"),
    [
        ("Senior Backend Java Developer", "rankings-senior-backend-java-developer.csv"),
        ("C++ / Rust Engineer (Remote)", "rankings-c-rust-engineer-remote.csv"),
        ('"; rm -rf /', "rankings-rm-rf.csv"),  # nothing that can break the header
        ("!!!", "rankings-job.csv"),
    ],
)
def test_export_filename(title: str, filename: str) -> None:
    assert export_filename(title) == filename


def record(name: str, phone: str | None = None) -> RankingRecord:
    return RankingRecord(
        rank=1,
        resume_id=uuid.uuid4(),
        name=name,
        email="a@example.com",
        phone=phone,
        filename="cv.pdf",
        current_title="Engineer",
        total_months=60,
        relevant_months=54,
        overall_score=Decimal("88.50"),
        verdict="strong",
        skill_score=Decimal("0.900"),
        semantic_score=None,
        experience_score=Decimal("1.000"),
        education_score=Decimal("1.000"),
        required_skill_coverage=Decimal("1.000"),
        matched_skills=[{"skill": "Java"}, {"skill": "Docker"}],
        missing_skills=[{"skill": "AWS"}],
        is_stale=False,
        parse_confidence=Decimal("0.90"),
    )


def test_csv_has_one_row_per_candidate_under_the_header() -> None:
    rows = list(csv.reader(io.StringIO(rankings_csv([record("Asha Rao")]))))
    assert rows[0] == CSV_COLUMNS
    assert dict(zip(CSV_COLUMNS, rows[1], strict=True)) == {
        "Rank": "1", "Name": "Asha Rao", "Email": "a@example.com", "Phone": "",
        "Current title": "Engineer", "Total years": "5.0", "Relevant years": "4.5",
        "Match %": "88.50", "Verdict": "strong", "Skills": "0.900", "Semantic": "",
        "Experience": "1.000", "Education": "1.000", "Required skill coverage": "1.000",
        "Matched skills": "Java; Docker", "Missing skills": "AWS", "File": "cv.pdf", "Stale": "",
    }  # fmt: skip


@pytest.mark.parametrize("name", ["=HYPERLINK(1)", "+SUM(A1)", "-1+1", "@cmd", "\tx"])
def test_cells_a_spreadsheet_would_run_are_escaped(name: str) -> None:
    rows = list(csv.reader(io.StringIO(rankings_csv([record(name)]))))
    assert rows[1][1] == "'" + name


def test_phone_numbers_stay_text() -> None:
    rows = list(csv.reader(io.StringIO(rankings_csv([record("Asha", phone="+919845012345")]))))
    assert rows[1][3] == "'+919845012345"  # Excel would turn +91... into a number
