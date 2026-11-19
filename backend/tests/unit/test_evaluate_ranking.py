"""The ranking evaluation's own arithmetic (scripts/evaluate_ranking.py), without the model."""

import importlib.util
from types import ModuleType
from typing import Any

import pytest

from tests.samples import SAMPLES


@pytest.fixture(scope="module")
def script() -> ModuleType:
    path = SAMPLES.parent / "scripts" / "evaluate_ranking.py"
    spec = importlib.util.spec_from_file_location("evaluate_ranking", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ranks_average_ties(script: ModuleType) -> None:
    assert script._ranks([10.0, 30.0, 20.0, 20.0]) == [1.0, 4.0, 2.5, 2.5]


@pytest.mark.parametrize(
    ("xs", "ys", "rho"),
    [
        ([1, 2, 3, 4], [10, 20, 30, 40], 1.0),
        ([1, 2, 3, 4], [40, 30, 20, 10], -1.0),
        ([1, 2, 3, 4, 5], [2, 1, 4, 3, 5], 0.8),  # textbook: 1 - 6*4 / (5*24)
        ([1, 1, 1], [1, 2, 3], 0.0),  # no spread: no correlation
    ],
)
def test_spearman(script: ModuleType, xs: list[float], ys: list[float], rho: float) -> None:
    assert script.spearman(xs, ys) == pytest.approx(rho)


def test_precision_at_k_uses_the_number_of_strong_samples(script: ModuleType) -> None:
    def row(persona: int, tier: str) -> Any:
        return script.Scored(persona, f"{persona}.pdf", tier, None)

    ranked = [
        (row(9, "strong"), 97.4),
        (row(1, "strong"), 96.9),
        (row(11, "good"), 91.9),
        (row(3, "strong"), 89.2),
        (row(13, "weak"), 8.0),
    ]
    result = script.metrics(ranked)
    assert (result["k"], result["precision"]) == (3, pytest.approx(2 / 3))
    assert (result["top3"], result["last"]) == ([9, 1, 11], 13)
    # Score ranks [5, 4, 3, 2, 1] against tier ranks [4, 4, 2, 4, 1]: 6 / sqrt(80).
    assert result["spearman"] == pytest.approx(6 / 80**0.5)
