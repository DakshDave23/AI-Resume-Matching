"""Combining the four components (§6.1): bounds, rescaling, the worked example."""

import random

import pytest

from app.services.matching.scorer import combine
from app.services.matching.scoring_config import COMPONENTS, DEFAULT_WEIGHTS


def components(
    skills: float | None, semantic: float | None, experience: float | None, education: float | None
) -> dict[str, float | None]:
    return dict(zip(COMPONENTS, (skills, semantic, experience, education), strict=True))


def test_the_worked_example() -> None:
    """Design doc §6.6: Candidate A 83%, Candidate C 57%."""
    a = combine(components(0.731, 0.798, 1.0, 1.0), DEFAULT_WEIGHTS)
    c = combine(components(0.538, 0.500, 0.5, 1.0), DEFAULT_WEIGHTS)
    assert a.score == pytest.approx(40 * 0.731 + 30 * 0.798 + 20 + 10)  # 83.2
    assert c.score == pytest.approx(40 * 0.538 + 15 + 10 + 10)  # 56.5
    assert (round(a.score), round(c.score)) == (83, 57)


def test_an_inactive_component_drops_out_and_the_rest_are_rescaled() -> None:
    result = combine(components(0.5, 1.0, None, 1.0), DEFAULT_WEIGHTS)  # no years in the JD
    assert result.effective_weights == pytest.approx(
        {"skills": 0.5, "semantic": 0.375, "experience": 0.0, "education": 0.125}
    )
    assert result.score == pytest.approx(100 * (0.5 * 0.5 + 0.375 + 0.125))
    assert result.components["experience"] is None


def test_only_one_active_component_is_the_whole_score() -> None:
    result = combine(components(0.62, None, None, None), DEFAULT_WEIGHTS)
    assert result.score == pytest.approx(62.0)
    assert result.effective_weights["skills"] == 1.0


def test_equivalent_experience_halves_educations_weight() -> None:
    full = combine(components(1.0, 1.0, 1.0, 0.0), DEFAULT_WEIGHTS)
    halved = combine(components(1.0, 1.0, 1.0, 0.0), DEFAULT_WEIGHTS, education_factor=0.5)
    assert full.score == pytest.approx(90.0)
    assert halved.score == pytest.approx(100 * 0.9 / 0.95)  # education is 0.05 of 0.95
    assert halved.effective_weights["education"] == pytest.approx(0.05 / 0.95)


def test_weights_are_relative() -> None:
    weights = {"skills": 2.0, "semantic": 1.0, "experience": 1.0, "education": 0.0}
    result = combine(components(1.0, 0.0, 0.5, 0.0), weights)
    assert result.score == pytest.approx(100 * (2 * 1.0 + 0 + 0.5) / 4)


@pytest.mark.parametrize(
    ("values", "weights"),
    [
        ((None, None, None, None), DEFAULT_WEIGHTS),  # nothing to match on
        ((1.0, 1.0, 1.0, 1.0), dict.fromkeys(COMPONENTS, 0.0)),  # every weight at 0
        ((None, None, None, 1.0), {"skills": 1.0, "semantic": 0, "experience": 0, "education": 0}),
    ],
)
def test_nothing_to_weigh_scores_zero(
    values: tuple[float | None, ...], weights: dict[str, float]
) -> None:
    result = combine(components(*values), weights)
    assert result.score == 0.0
    assert sum(result.effective_weights.values()) == 0.0


def test_scores_always_stay_within_0_and_100() -> None:
    rng = random.Random(26)
    for _ in range(2000):
        values = [rng.choice([None, rng.random(), 0.0, 1.0]) for _ in COMPONENTS]
        weights = {name: rng.choice([0.0, rng.random() * 3, 1.0]) for name in COMPONENTS}
        result = combine(components(*values), weights, education_factor=rng.choice([0.5, 1.0]))
        assert 0.0 <= result.score <= 100.0
        total = sum(result.effective_weights.values())
        assert total == pytest.approx(1.0) or total == 0.0
        active = [name for name, v in zip(COMPONENTS, values, strict=True) if v is not None]
        assert all(result.effective_weights[n] == 0.0 for n in COMPONENTS if n not in active)


def test_all_perfect_is_100_and_all_zero_is_0() -> None:
    assert combine(components(1, 1, 1, 1), DEFAULT_WEIGHTS).score == pytest.approx(100.0)
    assert combine(components(0, 0, 0, 0), DEFAULT_WEIGHTS).score == 0.0
