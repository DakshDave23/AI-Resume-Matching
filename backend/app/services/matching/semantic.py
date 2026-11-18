"""Semantic similarity: how well the resume's passages cover the JD (design doc §6.3).

    b_i     = max_k cos(requirement_i, chunk_k)        best passage per requirement
    coverage = weighted mean of b_i                      required 1.0, preferred 0.5
    raw     = 0.7 * coverage + 0.3 * cos(JD, resume)     whole-document vectors
    S_sem   = clip((raw - L) / (H - L), 0, 1)            calibrated on the samples

Years and degree sentences are left to the experience and education components
(see scoring_config). Each requirement keeps its best passage, which becomes the
requirement table in the candidate view: covered, partial or not covered.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from app.models.enums import RequirementCategory, RequirementType
from app.services.matching import scoring_config as config
from app.services.matching.skills import Passage
from app.services.nlp.vectors import Vector

MAX_EVIDENCE_CHARS = 1000


class Coverage(StrEnum):
    COVERED = "covered"
    PARTIAL = "partial"
    NOT_COVERED = "not_covered"


@dataclass(frozen=True)
class RequirementInput:
    requirement_id: int | None
    text: str
    category: RequirementCategory
    requirement_type: RequirementType
    vector: Vector


@dataclass(frozen=True)
class RequirementMatch:
    requirement_id: int | None
    text: str
    requirement_type: RequirementType
    weight: float
    similarity: float  # cosine with the best passage
    status: Coverage
    evidence: str | None  # the best passage, on one line
    evidence_section: str | None


@dataclass(frozen=True)
class SemanticScore:
    matches: tuple[RequirementMatch, ...]  # in JD order
    coverage: float
    document_similarity: float
    raw: float
    score: float  # S_sem, 0-1


def status_of(similarity: float) -> Coverage:
    if similarity >= config.COVERED_MIN_COSINE:
        return Coverage.COVERED
    if similarity >= config.PARTIAL_MIN_COSINE:
        return Coverage.PARTIAL
    return Coverage.NOT_COVERED


def calibrate(raw: float) -> float:
    low, high = config.SEMANTIC_FLOOR, config.SEMANTIC_CEILING
    return min(1.0, max(0.0, (raw - low) / (high - low)))


def _clip(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= MAX_EVIDENCE_CHARS else text[: MAX_EVIDENCE_CHARS - 1] + "…"


def semantic_score(
    requirements: Sequence[RequirementInput],
    passages: Sequence[Passage],
    *,
    job_vector: Vector | None,
    resume_vector: Vector | None,
) -> SemanticScore | None:
    """None when the JD has no requirement sentences to cover: the component drops out.

    A resume with no passages at all covers nothing and scores 0.
    """
    scored = [r for r in requirements if r.category.value not in config.NOT_SEMANTIC_CATEGORIES]
    if not scored:
        return None

    weights = np.array(
        [
            config.REQUIRED_SKILL_WEIGHT
            if r.requirement_type == RequirementType.REQUIRED
            else config.PREFERRED_SKILL_WEIGHT
            for r in scored
        ]
    )
    if passages:
        similarities = (
            np.stack([r.vector for r in scored]) @ np.stack([p.vector for p in passages]).T
        )
        best_index = similarities.argmax(axis=1)
        best = similarities[np.arange(len(scored)), best_index]
    else:
        best_index = np.full(len(scored), -1)
        best = np.zeros(len(scored))

    matches = []
    for requirement, weight, index, similarity in zip(
        scored, weights, best_index, best, strict=True
    ):
        passage = passages[int(index)] if index >= 0 else None
        matches.append(
            RequirementMatch(
                requirement_id=requirement.requirement_id,
                text=requirement.text,
                requirement_type=requirement.requirement_type,
                weight=float(weight),
                similarity=round(float(similarity), 3),
                status=status_of(float(similarity)),
                evidence=_clip(passage.text) if passage else None,
                evidence_section=passage.section if passage else None,
            )
        )

    coverage = float((weights * best).sum() / weights.sum())
    document = (
        float(job_vector @ resume_vector)
        if job_vector is not None and resume_vector is not None
        else 0.0
    )
    raw = config.COVERAGE_SHARE * coverage + config.DOCUMENT_SHARE * document
    return SemanticScore(
        matches=tuple(matches),
        coverage=coverage,
        document_similarity=document,
        raw=raw,
        score=calibrate(raw),
    )
