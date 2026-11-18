"""Semantic score arithmetic with hand-made vectors (§6.3)."""

import math

import numpy as np
import pytest

from app.models.enums import RequirementCategory, RequirementType
from app.services.matching import scoring_config as config
from app.services.matching.semantic import (
    Coverage,
    RequirementInput,
    calibrate,
    semantic_score,
    status_of,
)
from app.services.matching.skills import Passage
from app.services.nlp.vectors import Vector

REQ, PREF = RequirementType.REQUIRED, RequirementType.PREFERRED
SKILL, RESP = RequirementCategory.SKILL, RequirementCategory.RESPONSIBILITY


def unit(*xs: float) -> Vector:
    v = np.array(xs, dtype=np.float32)
    return (v / np.linalg.norm(v)).astype(np.float32)


def at(c: float, axis: int = 0) -> Vector:
    """Cosine `c` with the unit vector on `axis` (in 3 dimensions)."""
    v = np.zeros(3, np.float32)
    v[axis] = c
    v[(axis + 1) % 3] = math.sqrt(1 - c * c)
    return v


def requirement(
    text: str,
    vector: Vector,
    kind: RequirementType = REQ,
    category: RequirementCategory = SKILL,
) -> RequirementInput:
    return RequirementInput(None, text, category, kind, vector)


E0, E1 = unit(1, 0, 0), unit(0, 1, 0)


def test_each_requirement_takes_its_best_passage() -> None:
    result = semantic_score(
        [requirement("Build APIs", E0), requirement("Lead a team", E1)],
        [
            Passage("summary", "Backend developer.", at(0.3)),
            Passage("experience", "Dev | Acme\n- Built APIs.", at(0.8)),
        ],
        job_vector=None,
        resume_vector=None,
    )
    assert result is not None
    first, second = result.matches
    assert (first.similarity, first.status) == (0.8, Coverage.COVERED)
    assert first.evidence_section == "experience"
    assert first.evidence == "Dev | Acme - Built APIs."  # one line
    assert second.similarity == pytest.approx(round(math.sqrt(1 - 0.3**2), 3))


def test_coverage_is_the_weighted_mean_and_raw_mixes_in_the_document() -> None:
    passage = Passage("experience", "x", E0)
    result = semantic_score(
        [requirement("a", at(0.6), REQ), requirement("b", at(0.3), PREF)],
        [passage],
        job_vector=unit(1, 1, 0),
        resume_vector=unit(1, 0, 0),
    )
    assert result is not None
    coverage = (1.0 * 0.6 + 0.5 * 0.3) / 1.5
    document = 2**-0.5
    assert result.coverage == pytest.approx(coverage, abs=1e-6)
    assert result.document_similarity == pytest.approx(document, abs=1e-6)
    assert result.raw == pytest.approx(0.7 * coverage + 0.3 * document, abs=1e-6)
    assert result.score == pytest.approx(calibrate(result.raw))


@pytest.mark.parametrize(
    ("raw", "score"),
    [
        (0.10, 0.0),
        (config.SEMANTIC_FLOOR, 0.0),
        ((config.SEMANTIC_FLOOR + config.SEMANTIC_CEILING) / 2, 0.5),
        (config.SEMANTIC_CEILING, 1.0),
        (0.90, 1.0),
    ],
)
def test_calibration_stretches_and_clips(raw: float, score: float) -> None:
    assert calibrate(raw) == pytest.approx(score)


@pytest.mark.parametrize(
    ("similarity", "status"),
    [
        (config.COVERED_MIN_COSINE, Coverage.COVERED),
        (config.COVERED_MIN_COSINE - 0.001, Coverage.PARTIAL),
        (config.PARTIAL_MIN_COSINE, Coverage.PARTIAL),
        (config.PARTIAL_MIN_COSINE - 0.001, Coverage.NOT_COVERED),
    ],
)
def test_requirement_status(similarity: float, status: Coverage) -> None:
    assert status_of(similarity) == status


def test_years_and_degree_sentences_are_left_to_their_own_components() -> None:
    result = semantic_score(
        [
            requirement("4+ years of experience", E0, category=RequirementCategory.EXPERIENCE),
            requirement("Bachelor's in CS", E0, category=RequirementCategory.EDUCATION),
            requirement("Build APIs", E0, category=RESP),
        ],
        [Passage("experience", "x", E0)],
        job_vector=None,
        resume_vector=None,
    )
    assert result is not None
    assert [m.text for m in result.matches] == ["Build APIs"]


def test_a_jd_with_nothing_to_cover_drops_the_component() -> None:
    only_years = [requirement("5+ years", E0, category=RequirementCategory.EXPERIENCE)]
    assert semantic_score(only_years, [], job_vector=None, resume_vector=None) is None
    assert semantic_score([], [], job_vector=None, resume_vector=None) is None


def test_a_resume_without_passages_covers_nothing() -> None:
    result = semantic_score([requirement("Build APIs", E0)], [], job_vector=E0, resume_vector=None)
    assert result is not None
    (match,) = result.matches
    assert (match.similarity, match.status, match.evidence) == (0.0, Coverage.NOT_COVERED, None)
    assert (result.raw, result.score) == (0.0, 0.0)
