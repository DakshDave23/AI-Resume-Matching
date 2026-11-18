"""Education: does the candidate's degree meet the JD's (design doc §6.5)?

| Highest degree vs required     | Score |
| ------------------------------ | ----- |
| Equal or higher                | 1.0   |
| One level below                | 0.5   |
| Two or more below, or none     | 0.2   |

- Field of study: when the JD names fields and none of the candidate's degrees is in
  one of them (same equivalence group, or names with cosine >= 0.6), the score is
  multiplied by 0.8. A degree with no field written can't be judged: no penalty.
- "Or equivalent experience": education's weight is halved (`weight_factor`, applied
  when the components are combined), and relevant years >= the JD's minimum + 2
  stand in for the degree: 1.0.
- A JD that names no degree leaves the component out.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.models.enums import DegreeLevel
from app.services.matching import scoring_config as config
from app.services.nlp.embedder import TextEncoder


class FieldResult(StrEnum):
    NOT_REQUIRED = "not_required"  # the JD names no field
    MATCH = "match"
    DIFFERENT = "different"  # x 0.8
    UNKNOWN = "unknown"  # no field on the resume: no penalty


@dataclass(frozen=True)
class DegreeInput:
    degree: str | None  # as written: "B.Tech"
    level: int | None  # DegreeLevel
    field: str | None


@dataclass(frozen=True)
class EducationScore:
    score: float | None  # None when the JD names no degree: the component drops out
    weight_factor: float  # 0.5 when the JD accepts equivalent experience
    required_level: int | None
    candidate_level: int | None  # the highest found; None when no degree was found
    level_score: float | None
    required_fields: tuple[str, ...]
    field_result: FieldResult
    candidate_field: str | None  # the field that matched, else the highest degree's
    matched_field: str | None  # the JD field it matched
    waived_by_experience: bool  # "or equivalent experience" and enough relevant years

    @property
    def degree_found(self) -> bool:
        return self.candidate_level is not None


def level_score(candidate: int | None, required: int) -> float:
    if candidate is None or candidate < required - 1:
        return config.DEGREE_FAR_BELOW
    return config.DEGREE_MEETS if candidate >= required else config.DEGREE_ONE_BELOW


def _group(field: str) -> frozenset[str] | None:
    key = " ".join(field.split()).lower()
    return next((g for g in config.EQUIVALENT_FIELDS if key in g), None)


def same_field(a: str, b: str) -> bool:
    """Equal, or in one equivalence group ("Computer Applications" ~ "Computer Science")."""
    if " ".join(a.split()).lower() == " ".join(b.split()).lower():
        return True
    group = _group(a)
    return group is not None and group == _group(b)


def _match_field(
    fields: Sequence[str], required: Sequence[str], encoder: TextEncoder | None
) -> tuple[str, str] | None:
    """(candidate field, JD field) of the first match: by name or group, then by cosine."""
    for field in fields:
        for wanted in required:
            if same_field(field, wanted):
                return field, wanted
    if encoder is None or not fields:
        return None
    vectors = encoder.encode([*fields, *required])
    ours, theirs = vectors[: len(fields)], vectors[len(fields) :]
    similarities = ours @ theirs.T
    i, j = divmod(int(similarities.argmax()), len(required))
    if similarities[i, j] >= config.FIELD_MIN_COSINE:
        return fields[i], required[j]
    return None


def education_score(
    degrees: Sequence[DegreeInput],
    *,
    required_level: int | None,
    required_fields: Sequence[str] = (),
    accepts_equivalent_experience: bool = False,
    relevant_years: float | None = None,
    min_years: float | None = None,
    encoder: TextEncoder | None = None,
) -> EducationScore:
    """`encoder` compares field names the equivalence list doesn't cover (cosine >= 0.6)."""
    weight_factor = (
        config.EQUIVALENT_EXPERIENCE_WEIGHT_FACTOR if accepts_equivalent_experience else 1.0
    )
    levels = [d.level for d in degrees if d.level is not None]
    candidate_level = max(levels) if levels else None
    # Fields of real degrees (diploma and up), highest first.
    with_field = sorted(
        (d for d in degrees if d.field and (d.level or 0) >= DegreeLevel.DIPLOMA),
        key=lambda d: -(d.level or 0),
    )
    fields = [d.field for d in with_field if d.field]

    if not required_fields:
        field_result, candidate_field, matched = FieldResult.NOT_REQUIRED, None, None
    elif not fields:
        field_result, candidate_field, matched = FieldResult.UNKNOWN, None, None
    elif found := _match_field(fields, required_fields, encoder):
        field_result, (candidate_field, matched) = FieldResult.MATCH, found
    else:
        field_result, candidate_field, matched = FieldResult.DIFFERENT, fields[0], None

    if required_level is None:
        score, level = None, None
    else:
        level = level_score(candidate_level, required_level)
        score = level * (
            config.FIELD_MISMATCH_FACTOR if field_result == FieldResult.DIFFERENT else 1.0
        )

    waived = bool(  # only reported when it changes something
        score is not None
        and score < 1.0
        and accepts_equivalent_experience
        and min_years is not None
        and relevant_years is not None
        and relevant_years >= min_years + config.EQUIVALENT_EXPERIENCE_EXTRA_YEARS
    )
    return EducationScore(
        score=1.0 if waived else score,
        weight_factor=weight_factor,
        required_level=required_level,
        candidate_level=candidate_level,
        level_score=level,
        required_fields=tuple(required_fields),
        field_result=field_result,
        candidate_field=candidate_field,
        matched_field=matched,
        waived_by_experience=waived,
    )
