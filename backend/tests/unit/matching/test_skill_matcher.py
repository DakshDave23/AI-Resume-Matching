"""Tier rules with hand-made vectors, so every cosine is known exactly."""

import math

import numpy as np
import pytest

from app.models.enums import RequirementType
from app.services.matching import scoring_config as config
from app.services.matching.skills import (
    CandidateSkillInput,
    JobSkillInput,
    Passage,
    PreparedJob,
    SkillScore,
    Tier,
    match_skills,
    prepare_job,
)
from app.services.nlp.vectors import Vector
from tests.fakes import FakeEncoder

REQ, PREF = RequirementType.REQUIRED, RequirementType.PREFERRED
X = np.array([1.0, 0.0, 0.0], dtype=np.float32)


def at_cosine(c: float) -> Vector:
    """A unit vector whose cosine with X is exactly `c`."""
    return np.array([c, math.sqrt(1 - c * c), 0.0], dtype=np.float32)


def job_skill(
    name: str,
    *,
    category: str = "database",
    kind: RequirementType = REQ,
    min_years: float | None = None,
    vector: Vector | None = X,
    skill_id: int | None = None,
    is_custom: bool = False,
) -> JobSkillInput:
    weight = 1.0 if kind == REQ else 0.5
    return JobSkillInput(
        skill_id=skill_id if skill_id is not None else abs(hash(name)) % 10_000,
        name=name,
        category=category,
        requirement_type=kind,
        weight=weight,
        min_years=min_years,
        vector=vector,
        is_custom=is_custom,
    )


def resume_skill(
    name: str,
    *,
    terms: tuple[str, ...] | None = None,
    category: str = "database",
    years: float | None = None,
    vector: Vector | None = None,
    skill_id: int | None = None,
) -> CandidateSkillInput:
    return CandidateSkillInput(
        skill_id=skill_id if skill_id is not None else abs(hash(name)) % 10_000,
        name=name,
        category=category,
        terms=terms if terms is not None else (name,),
        years_used=years,
        evidence=f"Used {name} daily.",
        vector=vector,
    )


def score(
    skills: list[JobSkillInput],
    candidate: list[CandidateSkillInput],
    passages: list[Passage] | None = None,
    *,
    context: dict[str, Vector] | None = None,
    text: str = "",
) -> SkillScore:
    names = context if context is not None else {s.name: np.zeros(3, np.float32) for s in skills}
    job = PreparedJob(tuple(skills), names)
    return match_skills(job, candidate, passages or [], resume_text=text)


def only(result: SkillScore) -> tuple[Tier, float]:
    (match,) = result.matches
    return match.tier, match.credit


# --- Tiers 1 and 2 ----------------------------------------------------------------------------


def test_the_canonical_name_is_exact() -> None:
    assert only(score([job_skill("Kubernetes")], [resume_skill("Kubernetes")])) == (Tier.EXACT, 1)


def test_an_alias_or_fuzzy_spelling_is_alias() -> None:
    found = resume_skill("Kubernetes", terms=("k8s", "Kubernetis"))
    assert only(score([job_skill("Kubernetes")], [found])) == (Tier.ALIAS, 1)


def test_one_canonical_mention_is_enough_for_exact() -> None:
    found = resume_skill("Kubernetes", terms=("k8s", "kubernetes"))  # case doesn't matter
    assert only(score([job_skill("Kubernetes")], [found]))[0] == Tier.EXACT


@pytest.mark.parametrize(
    ("used", "credit"),
    [(5.0, 1.0), (4.0, 1.0), (3.0, 0.75), (1.0, 0.5), (None, 0.5)],
    ids=["more", "equal", "fewer", "far-fewer", "no-dated-role"],
)
def test_the_years_check(used: float | None, credit: float) -> None:
    result = score([job_skill("Java", min_years=4)], [resume_skill("Java", years=used)])
    assert only(result) == (Tier.EXACT, credit)
    assert result.matches[0].years_used == used


def test_no_min_years_no_years_check() -> None:
    assert only(score([job_skill("Java")], [resume_skill("Java", years=None)])) == (Tier.EXACT, 1)


# --- Tier 3 -----------------------------------------------------------------------------------


def test_a_close_skill_of_the_same_category_is_related() -> None:
    result = score([job_skill("PostgreSQL")], [resume_skill("MySQL", vector=at_cosine(0.62))])
    match = result.matches[0]
    assert (match.tier, match.credit, match.matched_skill) == (Tier.RELATED, 0.5, "MySQL")
    assert match.similarity == pytest.approx(0.62, abs=1e-3)
    assert match.evidence == "Used MySQL daily."


@pytest.mark.parametrize(
    ("cosine", "tier"),
    [
        (config.RELATED_MIN_COSINE + 0.001, Tier.RELATED),  # float32 rounding: just above
        (config.RELATED_MIN_COSINE - 0.01, Tier.MISSING),
    ],
)
def test_the_related_threshold(cosine: float, tier: Tier) -> None:
    result = score([job_skill("PostgreSQL")], [resume_skill("MySQL", vector=at_cosine(cosine))])
    assert only(result)[0] == tier


def test_related_needs_the_same_category() -> None:
    other = resume_skill("Redis Streams", category="messaging", vector=at_cosine(0.95))
    assert only(score([job_skill("PostgreSQL")], [other]))[0] == Tier.MISSING


def test_the_closest_related_skill_wins() -> None:
    result = score(
        [job_skill("PostgreSQL")],
        [
            resume_skill("SQLite", vector=at_cosine(0.60)),
            resume_skill("MySQL", vector=at_cosine(0.70)),
        ],
    )
    assert result.matches[0].matched_skill == "MySQL"


@pytest.mark.parametrize(
    ("wanted", "has"), [("Java", "JavaScript"), ("C#", "C"), ("React", "React Native")]
)
def test_guarded_pairs_are_never_related(wanted: str, has: str) -> None:
    result = score(
        [job_skill(wanted, category="language")],
        [resume_skill(has, category="language", vector=at_cosine(0.99))],
    )
    assert only(result)[0] == Tier.MISSING


def test_the_same_skill_beats_a_related_one() -> None:
    result = score(
        [job_skill("PostgreSQL", skill_id=1)],
        [
            resume_skill("PostgreSQL", skill_id=1, terms=("Postgres",)),
            resume_skill("MySQL", skill_id=2, vector=at_cosine(0.99)),
        ],
    )
    assert only(result) == (Tier.ALIAS, 1)


# --- Tier 4 -----------------------------------------------------------------------------------

ROLE = "Engineer | Acme\n- Split a monolith into 8 independently deployed services."


def test_a_described_skill_is_contextual_with_the_passage_as_evidence() -> None:
    result = score(
        [job_skill("Microservices", category="concept")],
        [],
        [Passage("experience", ROLE, at_cosine(0.46))],
        context={"Microservices": X},
    )
    match = result.matches[0]
    assert (match.tier, match.credit) == (Tier.CONTEXTUAL, 0.5)
    assert match.evidence == " ".join(ROLE.split())  # the whole passage, on one line
    assert match.similarity == pytest.approx(0.46, abs=1e-3)


@pytest.mark.parametrize(
    ("cosine", "tier"),
    [
        (config.CONTEXT_MIN_COSINE + 0.001, Tier.CONTEXTUAL),
        (config.CONTEXT_MIN_COSINE - 0.01, Tier.MISSING),
    ],
)
def test_the_contextual_threshold(cosine: float, tier: Tier) -> None:
    result = score(
        [job_skill("Microservices")],
        [],
        [Passage("experience", ROLE, at_cosine(cosine))],
        context={"Microservices": X},
    )
    assert only(result)[0] == tier


def test_the_summary_is_not_described_work() -> None:
    result = score(
        [job_skill("Microservices")],
        [],
        [Passage("summary", "Microservices enthusiast.", at_cosine(0.9))],
        context={"Microservices": X},
    )
    assert only(result)[0] == Tier.MISSING


def test_a_passage_naming_the_guarded_twin_never_counts() -> None:
    result = score(
        [job_skill("Java", category="language")],
        [],
        [Passage("experience", "Dev | Acme\n- Built JavaScript widgets.", at_cosine(0.9))],
        context={"Java": X},
    )
    assert only(result)[0] == Tier.MISSING


def test_related_comes_before_contextual() -> None:
    result = score(
        [job_skill("Kafka", category="messaging")],
        [resume_skill("RabbitMQ", category="messaging", vector=at_cosine(0.59))],
        [Passage("experience", ROLE, at_cosine(0.9))],
        context={"Kafka": X},
    )
    assert only(result)[0] == Tier.RELATED


# --- Custom skills ---------------------------------------------------------------------------


def test_a_custom_skill_is_found_in_the_resume_text() -> None:
    custom = job_skill("Quantum Widgets", is_custom=True, vector=None)
    found = score([custom], [], text="Asha Rao\nBuilt quantum widgets for trading desks.\n")
    match = found.matches[0]
    assert (match.tier, match.evidence) == (Tier.EXACT, "Built quantum widgets for trading desks.")
    missing = score([custom], [], text="Built quantum widgetsmith tools")  # whole words only
    assert only(missing)[0] == Tier.MISSING


# --- The score --------------------------------------------------------------------------------


def test_score_is_weighted_credit_over_weight() -> None:
    result = score(
        [
            job_skill("Java", skill_id=1),  # exact: 1.0 x 1.0
            job_skill("AWS", skill_id=2),  # missing: 0 x 1.0
            job_skill("Docker", skill_id=3, kind=PREF),  # exact: 1.0 x 0.5
        ],
        [resume_skill("Java", skill_id=1), resume_skill("Docker", skill_id=3)],
    )
    assert result.score == pytest.approx(1.5 / 2.5)
    assert (result.required_matched, result.required_total) == (1, 2)
    assert result.required_coverage == 0.5


def test_a_jd_without_skills_drops_the_component() -> None:
    result = score([], [resume_skill("Java")])
    assert (result.score, result.required_coverage, result.matches) == (None, None, ())


def test_prepare_job_embeds_the_names_once() -> None:
    encoder = FakeEncoder()
    prepared = prepare_job([job_skill("Kafka"), job_skill("Docker")], encoder)
    assert encoder.calls == [["Kafka", "Docker"]]
    assert set(prepared.name_vectors) == {"Kafka", "Docker"}
