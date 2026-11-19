"""Turn a match result into reasons a recruiter can check (design doc §6.6 and §7).

Every number here comes from the score itself, so the reasons always agree with it:

- Each active component has points available (100 x its effective weight), split into
  points earned (available x score) and points lost. Earned points add up to the
  match %, exactly as displayed: rounding is distributed so the parts sum to the total.
- Each JD skill's share of the skill points: available x w_j x m_j / sum(w). A skill
  credited at half, inferred, short on years or missing shows what it cost.
- Messages come from fixed templates (no LLM), sorted by points into strengths and gaps.
"""

import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any

from app.models.enums import DegreeLevel, RequirementType
from app.services.matching import scoring_config as config
from app.services.matching.education import FieldResult
from app.services.matching.scorer import MatchOutcome
from app.services.matching.semantic import Coverage
from app.services.matching.skills import SkillMatch, Tier

MINUS = chr(0x2212)  # U+2212 MINUS SIGN, as the design doc writes "minus 3.1 points"
LABELS = {
    "skills": "Skills",
    "semantic": "Semantic similarity",
    "experience": "Relevant experience",
    "education": "Education",
}
DEGREE_NAMES = {
    DegreeLevel.NONE: "no degree",
    DegreeLevel.HIGH_SCHOOL: "high school",
    DegreeLevel.DIPLOMA: "Diploma",
    DegreeLevel.BACHELOR: "Bachelor's",
    DegreeLevel.MASTER: "Master's",
    DegreeLevel.DOCTORATE: "Doctorate",
}
TIER_NOTES = {Tier.RELATED: "related", Tier.CONTEXTUAL: "inferred"}
MAX_SNIPPET_CHARS = 160


@dataclass(frozen=True)
class Item:
    """One reason. `impact` is in points: positive earned, negative lost."""

    type: str  # skill_match, skill_missing, requirement_match, semantic, experience, education
    impact: float
    message: str
    snippet: str | None = None
    section: str | None = None


def verdict(score: float) -> str:
    return next(name for low, name in config.VERDICT_BANDS if score >= low)


def round_to_total(values: Sequence[float], total: float, places: int = 1) -> list[float]:
    """Round each value so the rounded values sum to `total` rounded (largest remainder)."""
    scale = 10**places
    target = round(total * scale)
    floors = [math.floor(v * scale + 1e-9) for v in values]
    remainders = sorted(
        range(len(values)), key=lambda i: values[i] * scale - floors[i], reverse=True
    )
    for i in remainders[: max(0, target - sum(floors))]:
        floors[i] += 1
    return [f / scale for f in floors]


def _pts(points: float) -> str:
    return f"{MINUS}{abs(points):.1f} points"


def _years(value: float) -> str:
    return f"{value:g}"


def _snippet(text: str | None) -> str | None:
    if not text:
        return None
    text = " ".join(text.split())
    return text if len(text) <= MAX_SNIPPET_CHARS else text[: MAX_SNIPPET_CHARS - 1] + "…"


def _degree_name(level: int | None) -> str:
    return DEGREE_NAMES.get(DegreeLevel(level), str(level)) if level is not None else "a degree"


# --- The breakdown ------------------------------------------------------------------------


def breakdown(outcome: MatchOutcome) -> list[dict[str, Any]]:
    """Points available, earned and lost per component; earned adds up to the match %."""
    combined = outcome.combined
    available = [100 * combined.effective_weights[n] for n in config.COMPONENTS]
    earned_raw = [
        a * (combined.components[n] or 0.0)
        for a, n in zip(available, config.COMPONENTS, strict=True)
    ]
    earned = round_to_total(earned_raw, sum(earned_raw))
    shown_available = round_to_total(available, sum(available))
    return [
        {
            "component": name,
            "label": LABELS[name],
            "active": combined.components[name] is not None,
            "score": combined.components[name],
            "weight": combined.effective_weights[name],
            "available": avail,
            "earned": got,
            "lost": round(avail - got, 1),
        }
        for name, avail, got in zip(config.COMPONENTS, shown_available, earned, strict=True)
    ]


# --- Items --------------------------------------------------------------------------------


def _skill_items(outcome: MatchOutcome) -> list[Item]:
    matches = outcome.skills.matches
    total_weight = sum(m.weight for m in matches)
    if not matches or total_weight == 0:
        return []
    available = 100 * outcome.combined.effective_weights["skills"]
    items = []
    for m in matches:
        # Rounded one by one, so equal skills show equal points (the doc's 3.1 and 1.5);
        # the component totals in the breakdown are the exact ones.
        lost = round(available * m.weight * (1 - m.credit) / total_weight, 1)
        earned = round(available * m.weight * m.credit / total_weight, 1)
        items.extend(_skill_item(m, lost, earned))
    return items


def _skill_item(m: SkillMatch, lost: float, earned: float) -> list[Item]:
    kind = m.requirement_type.value
    if m.tier == Tier.MISSING:
        return [Item("skill_missing", -lost, f"Missing {kind} skill {m.name} ({_pts(lost)}).")]
    if m.tier == Tier.RELATED:
        message = (
            f"{m.name} credited at half: related skill {m.matched_skill} found ({_pts(lost)})."
        )
        return [Item("skill_match", -lost, message, _snippet(m.evidence), "skills")]
    if m.tier == Tier.CONTEXTUAL:
        # The whole passage earned the credit; the model can't single out the bullet,
        # so the message names the role and the snippet holds the passage.
        role = (m.evidence or "").split(" - ", 1)[0]
        source = f'the "{role}" role' if " | " in role else "the experience described"
        message = f"{m.name} not listed, but inferred from {source} ({_pts(lost)})."
        return [Item("skill_match", -lost, message, _snippet(m.evidence), "experience")]
    items = [Item("skill_match", earned, f"Has {m.name}.", _snippet(m.evidence))]
    if lost > 0 and m.min_years:  # the years check took a share
        used = _years(round(m.years_used or 0.0, 1))
        message = f"{m.name}: {used} of the {_years(m.min_years)} years asked for ({_pts(lost)})."
        items.append(Item("skill_match", -lost, message))
    return items


def _coverage_summary(outcome: MatchOutcome) -> str | None:
    required = [m for m in outcome.skills.matches if m.requirement_type == RequirementType.REQUIRED]
    if not required:
        return None
    found = [m for m in required if m.credit > 0]
    names = ", ".join(
        f"{m.name} ({TIER_NOTES[m.tier]})" if m.tier in TIER_NOTES else m.name for m in found
    )
    text = f"Has {len(found)} of {len(required)} required skills"
    return f"{text}: {names}." if found else f"{text}."


def _points(outcome: MatchOutcome, component: str) -> tuple[float, float]:
    """(earned, lost) for a component, exactly; items round their own numbers."""
    available = 100 * outcome.combined.effective_weights[component]
    earned = available * (outcome.combined.components[component] or 0.0)
    return earned, available - earned


def _semantic_items(outcome: MatchOutcome) -> list[Item]:
    semantic = outcome.semantic
    if semantic is None:
        return []
    earned, lost_exact = _points(outcome, "semantic")
    items = []
    covered = [m for m in semantic.matches if m.status == Coverage.COVERED]
    # The component's earned points, shared among covered requirements by similarity.
    weights = [m.weight * m.similarity for m in covered]
    shares = round_to_total(
        [earned * w / sum(weights) for w in weights] if weights else [], earned if weights else 0
    )
    for m, share in zip(covered, shares, strict=True):
        items.append(
            Item(
                "requirement_match",
                share,
                f'Strong match to "{m.text}" ({m.similarity:.2f}).',
                _snippet(m.evidence),
                m.evidence_section,
            )
        )
    lost = round(lost_exact, 1)
    if semantic.score < 1.0 and lost > 0:
        weak = [m for m in semantic.matches if m.status == Coverage.NOT_COVERED]
        text = f"Covers {len(covered)} of {len(semantic.matches)} job requirements well"
        if weak:  # name the most important one: required before preferred, then the weakest
            weakest = min(weak, key=lambda m: (-m.weight, m.similarity))
            text += f'; nothing in the resume matches "{weakest.text}"'
        items.append(Item("semantic", -lost, f"{text} ({_pts(lost)})."))
    return items


def _experience_items(outcome: MatchOutcome) -> list[Item]:
    exp = outcome.experience
    if exp.min_years is None or exp.score is None:
        return []
    earned, lost_exact = _points(outcome, "experience")
    have, need = f"{exp.relevant_years:.1f}", _years(exp.min_years)
    lost = round(lost_exact, 1)
    if exp.score >= 1.0:  # met: decided by the score, never by rounded points
        message = f"{have} years of relevant experience meets the {need}-year minimum."
        return [Item("experience", round(earned, 1), message)]
    return [
        Item(
            "experience",
            -lost,
            f"{have} of the {need} required years of relevant experience ({_pts(lost)}).",
        )
    ]


def _education_items(outcome: MatchOutcome) -> list[Item]:
    edu = outcome.education
    if edu.required_level is None or edu.score is None:
        return []
    earned_exact, lost_exact = _points(outcome, "education")
    earned, lost = round(earned_exact, 1), round(lost_exact, 1)
    required = _degree_name(edu.required_level)
    degree = edu.candidate_degree or _degree_name(edu.candidate_level)
    if edu.waived_by_experience:
        message = f"Relevant experience stands in for the {required} (the job accepts it)."
        return [Item("education", earned, message)]
    if edu.score >= 1.0:
        field = f" in {edu.candidate_field}" if edu.candidate_field else ""
        return [Item("education", earned, f"{degree}{field} meets the {required} requirement.")]
    if not edu.degree_found:
        message = f"No degree found; the job asks for a {required} ({_pts(lost)})."
    elif edu.field_result == FieldResult.DIFFERENT and (edu.level_score or 0) >= 1.0:
        fields = ", ".join(edu.required_fields)
        message = (
            f"{degree} in {edu.candidate_field} is outside the fields asked for "
            f"({fields}) ({_pts(lost)})."
        )
    else:
        message = f"{degree} is below the {required} requirement ({_pts(lost)})."
    return [Item("education", -lost, message)]


def _notes(outcome: MatchOutcome) -> list[str]:
    notes = []
    edu, exp = outcome.education, outcome.experience
    if edu.required_level is not None and not edu.degree_found:
        notes.append("Education not found; check the original file.")
    if exp.roles and not any(r.counted for r in exp.roles) and exp.relevant_months == 0:
        notes.append("No dated roles found; experience could not be measured.")
    if not outcome.skills.matches and not exp.roles:
        notes.append("Little could be read from this resume; check the original file.")
    if exp.above_max and exp.max_years is not None and exp.total_months is not None:
        notes.append(
            f"{exp.total_months / 12:.1f} years of experience is above the "
            f"{_years(exp.max_years)}-year maximum (shown for information, not penalised)."
        )
    return notes


# --- The explanation ---------------------------------------------------------------------


def explain(outcome: MatchOutcome) -> dict[str, Any]:
    """The `explanation` JSONB: verdict, summary, breakdown, strengths, gaps, notes."""
    parts = breakdown(outcome)
    items = [
        *_skill_items(outcome),
        *_semantic_items(outcome),
        *_experience_items(outcome),
        *_education_items(outcome),
    ]
    strengths = sorted((i for i in items if i.impact > 0), key=lambda i: -i.impact)
    gaps = sorted((i for i in items if i.impact < 0), key=lambda i: i.impact)
    score = round(sum(p["earned"] for p in parts), 1)
    band = verdict(outcome.score)
    summary = f"{band.capitalize()} match ({score:.0f}%)."
    if coverage := _coverage_summary(outcome):
        summary += f" {coverage}"
    return {
        "verdict": band,
        "score": score,
        "summary": summary,
        "breakdown": parts,
        "strengths": [asdict(i) for i in strengths[: config.TOP_ITEMS]],
        "gaps": [asdict(i) for i in gaps[: config.TOP_ITEMS]],
        "items": [asdict(i) for i in items],
        "notes": _notes(outcome),
    }
