"""Education rules (§6.5), with a stub encoder for the field cosine."""

from collections.abc import Sequence

import numpy as np
import pytest

from app.models.enums import DegreeLevel
from app.services.matching.education import (
    DegreeInput,
    EducationScore,
    FieldResult,
    education_score,
    level_score,
    same_field,
)
from app.services.nlp.embedder import Vectors

HS, DIP, BACH, MAST, PHD = (
    DegreeLevel.HIGH_SCHOOL,
    DegreeLevel.DIPLOMA,
    DegreeLevel.BACHELOR,
    DegreeLevel.MASTER,
    DegreeLevel.DOCTORATE,
)


class FieldVectors:
    """Encodes field names to fixed vectors, so cosines are chosen by the test."""

    model_name = "stub"

    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self.vectors = vectors

    def encode(self, texts: Sequence[str]) -> Vectors:
        rows = [np.array(self.vectors.get(t, [0.0, 0.0, 1.0]), dtype=np.float32) for t in texts]
        return np.stack([r / np.linalg.norm(r) for r in rows])


def degree(level: int | None, field: str | None = "Computer Science") -> DegreeInput:
    return DegreeInput("B.Tech", level, field)


def score(
    degrees: list[DegreeInput],
    *,
    required_level: int | None = BACH,
    required_fields: Sequence[str] = (),
    accepts_equivalent_experience: bool = False,
    relevant_years: float | None = None,
    min_years: float | None = None,
    encoder: FieldVectors | None = None,
) -> EducationScore:
    return education_score(
        degrees,
        required_level=required_level,
        required_fields=required_fields,
        accepts_equivalent_experience=accepts_equivalent_experience,
        relevant_years=relevant_years,
        min_years=min_years,
        encoder=encoder,
    )


@pytest.mark.parametrize(
    ("candidate", "required", "expected"),
    [
        (PHD, BACH, 1.0),
        (BACH, BACH, 1.0),
        (DIP, BACH, 0.5),  # one below
        (HS, BACH, 0.2),  # two below
        (None, BACH, 0.2),  # none found: not 0, the parser may have missed it
        (BACH, MAST, 0.5),
        (HS, DegreeLevel.NONE, 1.0),
    ],
)
def test_level_table(candidate: int | None, required: int, expected: float) -> None:
    assert level_score(candidate, required) == expected


def test_the_highest_degree_counts() -> None:
    result = score([degree(BACH), degree(MAST, "Statistics")], required_level=MAST)
    assert (result.candidate_level, result.level_score, result.score) == (MAST, 1.0, 1.0)


def test_no_degree_found_is_flagged_not_zero() -> None:
    result = score([])
    assert (result.score, result.degree_found) == (0.2, False)


def test_a_jd_without_a_degree_drops_the_component() -> None:
    assert score([degree(BACH)], required_level=None).score is None


# --- Field of study ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b", "same"),
    [
        ("Computer Science", "computer science", True),
        ("Computer Applications", "Computer Science", True),  # one group
        ("Computer Engineering", "Information Technology", True),
        ("Electronics and Communication", "Electrical Engineering", True),
        ("Statistics", "Mathematics", True),
        ("Electronics and Communication", "Computer Science", False),
        ("Accounting", "Computer Science", False),
    ],
)
def test_same_field(a: str, b: str, same: bool) -> None:
    assert same_field(a, b) is same


def test_a_matching_field_keeps_the_score() -> None:
    result = score([degree(BACH, "Computer Applications")], required_fields=["Computer Science"])
    assert (result.score, result.field_result, result.matched_field) == (
        1.0,
        FieldResult.MATCH,
        "Computer Science",
    )


def test_a_different_field_costs_a_fifth() -> None:
    result = score([degree(DIP, "Accounting")], required_fields=["Computer Science"])
    assert result.score == pytest.approx(0.5 * 0.8)
    assert (result.field_result, result.candidate_field) == (FieldResult.DIFFERENT, "Accounting")


def test_close_field_names_match_by_cosine() -> None:
    encoder = FieldVectors({"Data Science": [1, 0.8, 0], "Computer Science": [1, 0, 0]})
    result = score(
        [degree(BACH, "Data Science")], required_fields=["Computer Science"], encoder=encoder
    )  # cosine 0.78
    assert result.field_result == FieldResult.MATCH


def test_distant_field_names_do_not() -> None:
    encoder = FieldVectors({"Physics": [1, 1.5, 0], "Computer Science": [1, 0, 0]})
    result = score([degree(BACH, "Physics")], required_fields=["Computer Science"], encoder=encoder)
    assert result.field_result == FieldResult.DIFFERENT  # cosine 0.55


def test_any_degree_in_the_field_is_enough() -> None:
    result = score(
        [degree(MAST, "Statistics"), degree(BACH, "Computer Science")],
        required_fields=["Computer Science"],
    )
    assert (result.score, result.candidate_field) == (1.0, "Computer Science")


def test_a_school_leaving_certificate_has_no_field_to_judge() -> None:
    result = score([degree(HS, "Science")], required_fields=["Computer Science"])
    assert result.field_result == FieldResult.UNKNOWN  # no penalty on top of 0.2
    assert result.score == 0.2


def test_no_field_written_is_not_penalised() -> None:
    result = score([degree(BACH, None)], required_fields=["Computer Science"])
    assert (result.score, result.field_result) == (1.0, FieldResult.UNKNOWN)


def test_no_field_asked_for() -> None:
    assert score([degree(BACH, "Accounting")]).field_result == FieldResult.NOT_REQUIRED


# --- "Or equivalent experience" ---------------------------------------------------------------


def test_equivalent_experience_halves_the_weight() -> None:
    assert score([degree(BACH)], accepts_equivalent_experience=True).weight_factor == 0.5
    assert score([degree(BACH)]).weight_factor == 1.0


@pytest.mark.parametrize(("relevant_years", "waived"), [(5.0, True), (4.9, False)])
def test_enough_relevant_experience_stands_in_for_the_degree(
    relevant_years: float, waived: bool
) -> None:
    result = score(
        [degree(DIP, "Accounting")],
        accepts_equivalent_experience=True,
        relevant_years=relevant_years,
        min_years=3.0,  # needs 3 + 2 = 5
        required_fields=["Computer Science"],
    )
    assert result.waived_by_experience is waived
    assert result.score == (1.0 if waived else pytest.approx(0.4))


def test_without_the_clause_experience_does_not_replace_a_degree() -> None:
    result = score([degree(DIP)], relevant_years=20.0, min_years=3.0)
    assert (result.score, result.waived_by_experience) == (0.5, False)
