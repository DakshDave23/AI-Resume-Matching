"""Relevance factors and the month-by-month walk, with hand-made vectors (§6.4)."""

import math
from datetime import date

import numpy as np
import pytest

from app.services.matching import scoring_config as config
from app.services.matching.experience import (
    RoleInput,
    experience_score,
    profile_text,
    relevance_factor,
    role_profile,
)
from app.services.nlp.vectors import Vector
from tests.fakes import FakeEncoder

TODAY = date(2026, 11, 1)
PROFILE = np.array([1.0, 0.0], dtype=np.float32)
RELEVANT, PARTLY, UNRELATED = 0.70, 0.48, 0.30


def at(c: float) -> Vector:
    return np.array([c, math.sqrt(1 - c * c)], dtype=np.float32)


def role(
    start: str | None,
    end: str | None = None,
    *,
    similarity: float = RELEVANT,
    title: str = "Backend Engineer",
    internship: bool = False,
) -> RoleInput:
    def month(text: str | None) -> date | None:
        return date.fromisoformat(text + "-01") if text else None

    return RoleInput(
        title=title,
        company="Acme",
        start=month(start),
        end=month(end),
        is_current=start is not None and end is None,
        is_internship=internship,
        vector=at(similarity),
    )


def months(*roles: RoleInput, stated: int | None = None, min_years: float | None = 4) -> float:
    return experience_score(
        PROFILE, roles, today=TODAY, min_years=min_years, stated_months=stated
    ).relevant_months


@pytest.mark.parametrize(
    ("similarity", "factor"),
    [
        (config.RELEVANT_ROLE_MIN_COSINE, 1.0),
        (config.RELEVANT_ROLE_MIN_COSINE - 0.001, 0.5),
        (config.PARTLY_RELEVANT_ROLE_MIN_COSINE, 0.5),
        (config.PARTLY_RELEVANT_ROLE_MIN_COSINE - 0.001, 0.0),
        (None, 0.0),
    ],
)
def test_relevance_factor(similarity: float | None, factor: float) -> None:
    assert relevance_factor(similarity) == factor


def test_months_are_inclusive_and_present_is_today() -> None:
    assert months(role("2020-01", "2020-12")) == 12
    assert months(role("2025-12")) == 12  # Dec 2025 .. Nov 2026


def test_a_partly_relevant_role_counts_half() -> None:
    assert months(role("2020-01", "2020-12", similarity=PARTLY)) == 6


def test_an_unrelated_role_counts_nothing() -> None:
    assert months(role("2020-01", "2020-12", similarity=UNRELATED)) == 0


def test_overlapping_months_count_once_at_the_best_factor() -> None:
    full_time = role("2020-01", "2021-12", similarity=PARTLY)  # 24 months x 0.5
    side_job = role("2021-01", "2021-12", similarity=RELEVANT)  # its 12 months at 1.0 instead
    assert months(full_time, side_job) == 12 * 0.5 + 12 * 1.0


def test_internships_and_undated_roles_are_not_counted() -> None:
    intern = role("2024-06", "2024-11", title="Software Engineering Intern", internship=True)
    undated = role(None)
    result = experience_score(PROFILE, [intern, undated], today=TODAY, min_years=2)
    assert result.relevant_months == 0
    assert [r.counted for r in result.roles] == [False, False]
    assert result.roles[0].months == 6  # still shown with its length


def test_a_resume_without_dates_uses_its_stated_total() -> None:
    assert months(role(None), role(None, similarity=PARTLY), stated=84) == 84  # best factor 1.0
    assert months(role(None, similarity=PARTLY), stated=84) == 42
    assert months(role(None, similarity=UNRELATED), stated=84) == 0


def test_dated_roles_win_over_a_stated_total() -> None:
    assert months(role("2020-01", "2020-12"), stated=120) == 12


def test_a_future_end_date_stops_at_today() -> None:
    assert months(role("2026-10", "2027-03")) == 2


@pytest.mark.parametrize(
    ("relevant_months", "min_years", "score"),
    [(18, 4.0, 18 / 48), (48, 4.0, 1.0), (120, 4.0, 1.0), (0, 4.0, 0.0), (6, 0.0, 1.0)],
)
def test_score_is_relevant_years_over_the_minimum_capped_at_one(
    relevant_months: int, min_years: float, score: float
) -> None:
    roles = []
    if relevant_months:  # one current role, exactly that long
        start = TODAY.year * 12 + TODAY.month - relevant_months  # 0-based month index
        roles = [role(f"{start // 12}-{start % 12 + 1:02d}")]
    result = experience_score(PROFILE, roles, today=TODAY, min_years=min_years)
    assert result.relevant_months == relevant_months
    assert result.score == pytest.approx(score)


def test_no_minimum_drops_the_component_but_keeps_the_years() -> None:
    result = experience_score(PROFILE, [role("2020-01", "2020-12")], today=TODAY, min_years=None)
    assert (result.score, result.relevant_years) == (None, 1.0)


def test_above_the_maximum_is_information_only() -> None:
    result = experience_score(
        PROFILE, [role("2010-01")], today=TODAY, min_years=3, max_years=5, total_months=203
    )
    assert result.above_max is True
    assert result.score == 1.0  # never penalised


def test_the_role_profile_is_title_then_responsibilities_in_one_call() -> None:
    encoder = FakeEncoder()
    role_profile("Backend Developer", ["Build APIs.", "Run services."], encoder)
    assert encoder.calls == [["Backend Developer Build APIs. Run services."]]
    assert profile_text("Data Scientist", []) == "Data Scientist"
