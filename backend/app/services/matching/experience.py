"""Relevant experience: years spent in roles like this one (design doc §6.4).

1. The role profile is the JD's title plus its responsibility sentences, embedded as
   one text.
2. Each role (title + description, embedded when the resume was parsed) gets a
   factor from its cosine with the profile: relevant 1.0, partly relevant 0.5,
   unrelated 0.
3. The career is walked month by month. Each month counts once, at the highest factor
   of any role active that month, so overlapping jobs are never counted twice.
   Internships are listed but not counted, as in total experience.
4. Y_rel = sum of monthly factors / 12, and S_exp = min(1, Y_rel / M) for the JD's
   minimum M. A JD without a minimum leaves the component out.

Being above the JD's maximum is reported, never penalised: an over-qualification
penalty works as a proxy for age.

A resume without dates still states a total ("7 years of experience"): its relevant
months are that total times the best factor among its roles.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date

from app.services.matching import scoring_config as config
from app.services.nlp.embedder import TextEncoder
from app.services.nlp.vectors import Vector


@dataclass(frozen=True)
class RoleInput:
    title: str | None
    company: str | None
    start: date | None  # first of the month
    end: date | None  # None while current
    is_current: bool
    is_internship: bool
    vector: Vector | None  # title + description


@dataclass(frozen=True)
class RoleRelevance:
    title: str | None
    company: str | None
    start: date | None
    end: date | None
    months: int | None  # length of the role; None when undated
    similarity: float | None
    factor: float  # 1.0, 0.5 or 0
    is_internship: bool

    @property
    def counted(self) -> bool:
        """Dated and not an internship: its months go into relevant experience."""
        return self.start is not None and not self.is_internship


@dataclass(frozen=True)
class ExperienceScore:
    roles: tuple[RoleRelevance, ...]
    relevant_months: float
    total_months: int | None  # all experience, as parsed
    min_years: float | None
    max_years: float | None
    score: float | None  # None when the JD sets no minimum: the component drops out

    @property
    def relevant_years(self) -> float:
        return self.relevant_months / 12

    @property
    def above_max(self) -> bool:
        """Shown to the recruiter as information only."""
        return (
            self.max_years is not None
            and self.total_months is not None
            and self.total_months / 12 > self.max_years
        )


def profile_text(title: str, responsibilities: Sequence[str]) -> str:
    return "\n".join([title, *responsibilities]).strip()


def role_profile(title: str, responsibilities: Sequence[str], encoder: TextEncoder) -> Vector:
    """The JD's role profile: computed once per job, then reused for every resume."""
    vector: Vector = encoder.encode([profile_text(title, responsibilities)])[0]
    return vector


def relevance_factor(similarity: float | None) -> float:
    if similarity is None:
        return 0.0
    if similarity >= config.RELEVANT_ROLE_MIN_COSINE:
        return 1.0
    if similarity >= config.PARTLY_RELEVANT_ROLE_MIN_COSINE:
        return config.PARTLY_RELEVANT_FACTOR
    return 0.0


def _month(value: date) -> int:
    return value.year * 12 + value.month - 1


def experience_score(
    profile: Vector,
    roles: Sequence[RoleInput],
    *,
    today: date,
    min_years: float | None,
    max_years: float | None = None,
    total_months: int | None = None,
    stated_months: int | None = None,
) -> ExperienceScore:
    """`stated_months`: the total a resume without dates states, used when no role is dated."""
    now = _month(today)
    rated: list[RoleRelevance] = []
    best_by_month: dict[int, float] = {}
    for role in roles:
        similarity = round(float(role.vector @ profile), 3) if role.vector is not None else None
        factor = relevance_factor(similarity)
        rating = RoleRelevance(
            role.title,
            role.company,
            role.start,
            role.end,
            months=None,
            similarity=similarity,
            factor=factor,
            is_internship=role.is_internship,
        )
        if role.start is not None:
            first = _month(role.start)
            last = min(_month(role.end), now) if role.end is not None else now
            rating = replace(rating, months=max(0, last - first + 1))
            if rating.counted:
                for month in range(first, last + 1):
                    best_by_month[month] = max(best_by_month.get(month, 0.0), factor)
        rated.append(rating)

    relevant = float(sum(best_by_month.values()))
    if not any(r.counted for r in rated) and stated_months:
        best = max((r.factor for r in rated if not r.is_internship), default=0.0)
        relevant = stated_months * best

    if min_years is None:
        score = None
    elif min_years <= 0:
        score = 1.0
    else:
        score = min(1.0, relevant / 12 / min_years)
    return ExperienceScore(
        roles=tuple(rated),
        relevant_months=relevant,
        total_months=total_months,
        min_years=min_years,
        max_years=max_years,
        score=score,
    )
