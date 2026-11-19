"""Explanations (§7): points that add up, messages from templates, notes."""

import pytest

from app.models.enums import RequirementType
from app.services.matching.education import EducationScore, FieldResult
from app.services.matching.experience import ExperienceScore, RoleRelevance
from app.services.matching.explainer import MINUS, breakdown, explain, round_to_total, verdict
from app.services.matching.scorer import MatchOutcome, combine
from app.services.matching.scoring_config import DEFAULT_WEIGHTS
from app.services.matching.skills import SkillMatch, SkillScore, Tier

REQ, PREF = RequirementType.REQUIRED, RequirementType.PREFERRED


def skill(
    name: str, kind: RequirementType, tier: Tier, credit: float, **extra: object
) -> SkillMatch:
    fields: dict[str, object] = {
        "evidence": f"Used {name}.",
        "matched_skill": None,
        "similarity": None,
        "min_years": None,
        "years_used": None,
    } | extra
    weight = 1.0 if kind == REQ else 0.5
    return SkillMatch(name, kind, weight, tier, credit, **fields)  # type: ignore[arg-type]


CANDIDATE_A = (
    skill("Java", REQ, Tier.EXACT, 1.0),
    skill("Spring Boot", REQ, Tier.EXACT, 1.0),
    skill("PostgreSQL", REQ, Tier.RELATED, 0.5, matched_skill="MySQL", similarity=0.62),
    skill("REST APIs", REQ, Tier.ALIAS, 1.0),
    skill(
        "Microservices", REQ, Tier.CONTEXTUAL, 0.5, similarity=0.46,
        evidence="Java Developer | Contoso Payments - Split a monolith into 8 services.",
    ),
    skill("Docker", PREF, Tier.EXACT, 1.0),
    skill("Kafka", PREF, Tier.RELATED, 0.5, matched_skill="RabbitMQ", similarity=0.59),
    skill("AWS", PREF, Tier.MISSING, 0.0, evidence=None),
)  # fmt: skip


def experience(
    relevant_months: float, min_years: float | None = 4.0, **extra: object
) -> ExperienceScore:
    score = None if min_years is None else min(1.0, relevant_months / 12 / min_years)
    fields: dict[str, object] = {"total_months": 66, "max_years": None, "roles": ()} | extra
    return ExperienceScore(
        relevant_months=relevant_months,
        min_years=min_years,
        score=score,
        **fields,  # type: ignore[arg-type]
    )


def education(score: float | None = 1.0, **extra: object) -> EducationScore:
    fields: dict[str, object] = {
        "weight_factor": 1.0,
        "required_level": 3,
        "candidate_level": 3,
        "candidate_degree": "B.Tech",
        "level_score": score,
        "required_fields": ("Computer Science",),
        "field_result": FieldResult.MATCH,
        "candidate_field": "Computer Science",
        "matched_field": "Computer Science",
        "waived_by_experience": False,
    } | extra
    return EducationScore(score=score, **fields)  # type: ignore[arg-type]


def outcome(
    matches: tuple[SkillMatch, ...] = CANDIDATE_A,
    semantic: float | None = 1.0,  # all four active: the default 40/30/20/10 split
    exp: ExperienceScore | None = None,
    edu: EducationScore | None = None,
) -> MatchOutcome:
    exp = exp or experience(54)
    edu = edu or education()
    total = sum(m.weight for m in matches)
    skills = SkillScore(
        matches,
        sum(m.weight * m.credit for m in matches) / total if total else None,
        sum(m.credit > 0 for m in matches if m.requirement_type == REQ),
        sum(m.requirement_type == REQ for m in matches),
    )
    combined = combine(
        {
            "skills": skills.score,
            "semantic": semantic,
            "experience": exp.score,
            "education": edu.score,
        },
        DEFAULT_WEIGHTS,
        education_factor=edu.weight_factor,
    )
    return MatchOutcome(combined, skills, None, exp, edu, DEFAULT_WEIGHTS)


def gaps(result: MatchOutcome) -> dict[str, float]:
    return {g["message"]: g["impact"] for g in explain(result)["gaps"]}


# --- Points -------------------------------------------------------------------------------


def test_candidate_a_loses_the_doc_s_points_on_skills() -> None:
    """§6.6: 3.1 each for PostgreSQL, Microservices and AWS, 1.5 for Kafka; 10.8 in all."""
    result = explain(outcome(semantic=0.798))
    skill_part = next(p for p in result["breakdown"] if p["component"] == "skills")
    assert (skill_part["earned"], skill_part["lost"], skill_part["available"]) == (29.2, 10.8, 40.0)
    lost = {
        g["message"].split()[0]: g["impact"]
        for g in result["gaps"]
        if g["type"].startswith("skill")
    }
    assert lost == {"PostgreSQL": -3.1, "Microservices": -3.1, "Missing": -3.1, "Kafka": -1.5}


def test_breakdown_adds_up_to_the_match_percent() -> None:
    result = outcome(semantic=0.798)
    parts = breakdown(result)
    assert sum(p["earned"] for p in parts) == pytest.approx(round(result.score, 1))
    assert sum(p["available"] for p in parts) == pytest.approx(100.0)
    for part in parts:
        assert part["earned"] + part["lost"] == pytest.approx(part["available"])


def test_an_inactive_component_has_no_points() -> None:
    result = outcome(semantic=0.5, exp=experience(0, min_years=None))  # no years in the JD
    parts = {p["component"]: p for p in breakdown(result)}
    assert (parts["experience"]["active"], parts["experience"]["available"]) == (False, 0.0)
    assert sum(p["available"] for p in parts.values()) == pytest.approx(100.0)
    assert not any(i["type"] == "experience" for i in explain(result)["items"])


@pytest.mark.parametrize(
    "values",
    [[33.3333, 33.3333, 33.3334], [12.35, 12.35, 0.3], [0.04, 0.04, 0.04], [99.96, 0.0]],
)
def test_round_to_total_keeps_the_sum(values: list[float]) -> None:
    rounded = round_to_total(values, sum(values))
    assert sum(rounded) == pytest.approx(round(sum(values), 1))
    assert all(abs(r - v) < 0.1 for r, v in zip(rounded, values, strict=True))


@pytest.mark.parametrize(
    ("score", "band"),
    [(100, "strong"), (80, "strong"), (79.99, "good"), (65, "good"), (64.9, "partial"),
     (50, "partial"), (49.99, "weak"), (0, "weak")],
)  # fmt: skip
def test_verdict_bands(score: float, band: str) -> None:
    assert verdict(score) == band


# --- Messages -------------------------------------------------------------------------------


def test_skill_messages_follow_the_templates() -> None:
    messages = set(gaps(outcome(semantic=0.8)))
    assert f"Missing preferred skill AWS ({MINUS}3.1 points)." in messages
    assert (
        f"PostgreSQL credited at half: related skill MySQL found ({MINUS}3.1 points)." in messages
    )
    assert (
        f'Microservices not listed, but inferred from the "Java Developer | Contoso Payments" '
        f"role ({MINUS}3.1 points)."
    ) in messages


def test_the_summary_lists_required_skills_with_how_they_were_found() -> None:
    summary = explain(outcome(semantic=0.8))["summary"]
    assert summary.startswith("Strong match (")
    assert summary.endswith(
        "Has 5 of 5 required skills: Java, Spring Boot, PostgreSQL (related), REST APIs, "
        "Microservices (inferred)."
    )


def test_years_short_on_a_skill_shows_what_it_cost() -> None:
    java = skill("Java", REQ, Tier.EXACT, 0.5, min_years=4.0, years_used=1.5)
    result = gaps(outcome((java,)))
    assert f"Java: 1.5 of the 4 years asked for ({MINUS}20.0 points)." in result


def test_experience_met_and_short() -> None:
    met = explain(outcome(exp=experience(54)))["strengths"]
    assert any(
        s["message"] == "4.5 years of relevant experience meets the 4-year minimum." for s in met
    )
    short = gaps(outcome(exp=experience(18)))
    assert f"1.5 of the 4 required years of relevant experience ({MINUS}12.5 points)." in short


@pytest.mark.parametrize(
    ("edu", "message"),
    [
        (education(), "B.Tech in Computer Science meets the Bachelor's requirement."),
        (
            education(0.5, candidate_level=2, candidate_degree="Diploma"),
            f"Diploma is below the Bachelor's requirement ({MINUS}5.0 points).",
        ),
        (
            education(0.8, field_result=FieldResult.DIFFERENT, candidate_field="Accounting",
                      matched_field=None, level_score=1.0, candidate_degree="B.Com"),
            f"B.Com in Accounting is outside the fields asked for (Computer Science) "
            f"({MINUS}2.0 points).",
        ),
        (
            education(0.2, candidate_level=None, candidate_degree=None),
            f"No degree found; the job asks for a Bachelor's ({MINUS}8.0 points).",
        ),
        (
            education(1.0, waived_by_experience=True, weight_factor=0.5),
            "Relevant experience stands in for the Bachelor's (the job accepts it).",
        ),
    ],
)  # fmt: skip
def test_education_messages(edu: EducationScore, message: str) -> None:
    messages = [i["message"] for i in explain(outcome(edu=edu))["items"]]
    assert message in messages


def test_data_quality_notes() -> None:
    missing_degree = education(0.2, candidate_level=None, candidate_degree=None)
    notes = explain(outcome(edu=missing_degree))["notes"]
    assert "Education not found; check the original file." in notes

    undated = experience(0, roles=(RoleRelevance("Dev", None, None, None, None, 0.7, 1.0, False),))
    assert (
        "No dated roles found; experience could not be measured."
        in explain(outcome(exp=undated))["notes"]
    )

    senior = experience(150, max_years=8.0, total_months=150, roles=())
    assert any("above the 8-year maximum" in n for n in explain(outcome(exp=senior))["notes"])


def test_strengths_and_gaps_are_sorted_and_capped() -> None:
    result = explain(
        outcome(semantic=0.6, exp=experience(18), edu=education(0.5, candidate_level=2))
    )
    strengths = [s["impact"] for s in result["strengths"]]
    gap_points = [g["impact"] for g in result["gaps"]]
    assert strengths == sorted(strengths, reverse=True) and all(s > 0 for s in strengths)
    assert gap_points == sorted(gap_points) and all(g < 0 for g in gap_points)
    assert len(result["gaps"]) <= 5 and len(result["items"]) > len(result["gaps"])


def test_a_met_requirement_never_shows_a_rounding_loss() -> None:
    """With rescaled weights, rounded points can be 0.1 short; met is decided by the score."""
    result = explain(outcome(semantic=None, exp=experience(54)))  # 4.5 of 4 years
    messages = {i["message"]: i["impact"] for i in result["items"]}
    assert "4.5 years of relevant experience meets the 4-year minimum." in messages
    assert not any("of the 4 required years" in m for m in messages)
