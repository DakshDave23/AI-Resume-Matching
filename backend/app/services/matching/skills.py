"""The skill score: tiered matching of JD skills to resume evidence (design doc §6.2).

Each JD skill earns credit from the first tier that fires:

| Tier          | Rule                                                        | Credit |
| ------------- | ----------------------------------------------------------- | ------ |
| 1. exact      | The resume has the same skill, written as its canonical name | 1.0    |
| 2. alias      | The same skill through an alias or fuzzy match ("k8s")      | 1.0    |
| 3. related    | A resume skill of the same category, cosine >= RELATED_MIN  | 0.5    |
| 4. contextual | Not listed, but an experience or project chunk describes it | 0.5    |
| 5. missing    | None of the above                                           | 0      |

    S_skill = sum(w_j * m_j) / sum(w_j)     w = 1.0 required, 0.5 preferred

- Years check: when the JD sets min_years and the resume shows fewer years of the
  skill, tiers 1-2 are multiplied by max(0.5, used / required). A skill with no
  dated role behind it shows 0 years.
- Guard: tiers 3 and 4 never pair Java with JavaScript, C with C#, and so on; tier 3
  also needs the same category.
- A recruiter's custom skill is in no extractor dictionary, so tier 1 looks for its
  name in the resume text instead.

The matcher is pure: inputs come from `inputs.py` (the database) or the parsers.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from app.models.enums import RequirementType
from app.services.matching import scoring_config as config
from app.services.nlp.embedder import TextEncoder
from app.services.nlp.taxonomy import normalize_term
from app.services.nlp.vectors import Vector

# Tier 4 looks for a skill in described work only, not in the summary (§6.2).
CONTEXT_SECTIONS = frozenset({"experience", "projects"})
MAX_EVIDENCE_CHARS = 1000  # a whole chunk (up to 120 words) for tier 4


class Tier(StrEnum):
    EXACT = "exact"
    ALIAS = "alias"
    RELATED = "related"
    CONTEXTUAL = "contextual"
    MISSING = "missing"


@dataclass(frozen=True)
class JobSkillInput:
    skill_id: int
    name: str
    category: str
    requirement_type: RequirementType
    weight: float
    min_years: float | None
    vector: Vector | None  # the skill's "Name (category)" vector, for tier 3
    is_custom: bool = False


@dataclass(frozen=True)
class CandidateSkillInput:
    skill_id: int
    name: str
    category: str
    terms: tuple[str, ...]  # as written in the resume
    years_used: float | None
    evidence: str | None
    vector: Vector | None


@dataclass(frozen=True)
class Passage:
    """A chunk of the resume (summary, experience or projects), with its vector."""

    section: str
    text: str
    vector: Vector


@dataclass(frozen=True)
class SkillMatch:
    name: str
    requirement_type: RequirementType
    weight: float
    tier: Tier
    credit: float  # 0-1, after the years check
    evidence: str | None  # the resume text that earned the credit
    matched_skill: str | None  # tier 3: the related resume skill
    similarity: float | None  # tiers 3-4: the cosine that fired
    min_years: float | None
    years_used: float | None

    @property
    def weighted_credit(self) -> float:
        return self.weight * self.credit


@dataclass(frozen=True)
class SkillScore:
    matches: tuple[SkillMatch, ...]  # in the JD's skill order
    score: float | None  # None when the JD lists no skills: the component drops out
    required_matched: int  # required skills with any credit
    required_total: int

    @property
    def required_coverage(self) -> float | None:
        """'4 of 5 required skills', the number recruiters read first (§6.2)."""
        return self.required_matched / self.required_total if self.required_total else None


@dataclass(frozen=True)
class PreparedJob:
    """A job's skills plus what tier 4 needs, computed once per job, not per resume."""

    skills: tuple[JobSkillInput, ...]
    name_vectors: dict[str, Vector]  # bare skill names, for tier 4


def prepare_job(skills: Sequence[JobSkillInput], encoder: TextEncoder) -> PreparedJob:
    names = [s.name for s in skills]
    vectors = encoder.encode(names) if names else np.zeros((0, 0), np.float32)
    return PreparedJob(tuple(skills), dict(zip(names, vectors, strict=True)))


def _clip(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= MAX_EVIDENCE_CHARS else text[: MAX_EVIDENCE_CHARS - 1] + "…"


def _guarded(a: str, b: str) -> bool:
    return frozenset((a, b)) in config.NEVER_EQUIVALENT


def _guard_partners(name: str) -> list[str]:
    return [other for pair in config.NEVER_EQUIVALENT if name in pair for other in pair - {name}]


def _names(text: str, term: str) -> bool:
    """`term` appears as a whole word or phrase ("Java" is not in "JavaScript")."""
    return re.search(rf"(?<![\w.#+]){re.escape(term)}(?![\w#+])", text, re.IGNORECASE) is not None


def _years_factor(job: JobSkillInput, years_used: float | None) -> float:
    if not job.min_years:
        return 1.0
    ratio = (years_used or 0.0) / job.min_years
    return max(config.YEARS_CREDIT_FLOOR, min(1.0, ratio))


class _Matcher:
    def __init__(
        self,
        job: PreparedJob,
        candidate: Sequence[CandidateSkillInput],
        passages: Sequence[Passage],
        resume_text: str,
    ) -> None:
        self.job = job
        self.by_id = {s.skill_id: s for s in candidate}
        self.candidate = candidate
        self.passages = passages
        self.resume_text = resume_text

    def match(self, skill: JobSkillInput) -> SkillMatch:
        return (
            self._same_skill(skill)
            or self._custom_in_text(skill)
            or self._related(skill)
            or self._contextual(skill)
            or self._result(skill, Tier.MISSING, 0.0)
        )

    def _result(
        self,
        skill: JobSkillInput,
        tier: Tier,
        credit: float,
        *,
        evidence: str | None = None,
        matched: str | None = None,
        similarity: float | None = None,
        years_used: float | None = None,
    ) -> SkillMatch:
        return SkillMatch(
            name=skill.name,
            requirement_type=skill.requirement_type,
            weight=skill.weight,
            tier=tier,
            credit=credit,
            evidence=_clip(evidence) if evidence else None,
            matched_skill=matched,
            similarity=round(similarity, 3) if similarity is not None else None,
            min_years=skill.min_years,
            years_used=years_used,
        )

    # Tiers 1-2 -------------------------------------------------------------------------

    def _same_skill(self, skill: JobSkillInput) -> SkillMatch | None:
        found = self.by_id.get(skill.skill_id)
        if found is None:
            return None
        canonical = normalize_term(skill.name)
        written_as_is = any(normalize_term(t) == canonical for t in found.terms)
        tier = Tier.EXACT if written_as_is else Tier.ALIAS
        credit = _years_factor(skill, found.years_used)
        return self._result(
            skill, tier, credit, evidence=found.evidence, years_used=found.years_used
        )

    def _custom_in_text(self, skill: JobSkillInput) -> SkillMatch | None:
        if not skill.is_custom:
            return None
        for line in self.resume_text.split("\n"):
            if _names(line, skill.name):
                return self._result(skill, Tier.EXACT, _years_factor(skill, None), evidence=line)
        return None

    # Tier 3 ------------------------------------------------------------------------------

    def _related(self, skill: JobSkillInput) -> SkillMatch | None:
        if skill.vector is None:
            return None
        best: tuple[float, CandidateSkillInput] | None = None
        for other in self.candidate:
            if (
                other.vector is None
                or other.category != skill.category
                or _guarded(skill.name, other.name)
            ):
                continue
            cosine = float(skill.vector @ other.vector)
            if cosine >= config.RELATED_MIN_COSINE and (best is None or cosine > best[0]):
                best = (cosine, other)
        if best is None:
            return None
        cosine, other = best
        return self._result(
            skill,
            Tier.RELATED,
            config.PARTIAL_CREDIT,
            evidence=other.evidence,
            matched=other.name,
            similarity=cosine,
        )

    # Tier 4 ------------------------------------------------------------------------------

    def _contextual(self, skill: JobSkillInput) -> SkillMatch | None:
        query = self.job.name_vectors.get(skill.name)
        if query is None or not self.passages:
            return None
        partners = _guard_partners(skill.name)
        scored = [
            (float(p.vector @ query), p)
            for p in self.passages
            if p.section in CONTEXT_SECTIONS  # described work, not the summary's claims
            and not any(_names(p.text, partner) for partner in partners)  # "JavaScript" != Java
        ]
        if not scored:
            return None
        cosine, passage = max(scored, key=lambda pair: pair[0])
        if cosine < config.CONTEXT_MIN_COSINE:
            return None
        # The evidence is the whole passage: it is what scored. all-MiniLM-L6-v2 can't
        # single out the bullet reliably (on sample 3 it prefers the Docker bullet to
        # "split a monolith into 8 independently deployed services", 0.39 to 0.36).
        return self._result(
            skill, Tier.CONTEXTUAL, config.PARTIAL_CREDIT, evidence=passage.text, similarity=cosine
        )


def match_skills(
    job: PreparedJob,
    candidate: Sequence[CandidateSkillInput],
    passages: Sequence[Passage],
    *,
    resume_text: str = "",
) -> SkillScore:
    """Score one resume's skills against a prepared job. `resume_text` finds custom skills."""
    matcher = _Matcher(job, candidate, passages, resume_text)
    matches = tuple(matcher.match(skill) for skill in job.skills)
    total_weight = sum(m.weight for m in matches)
    required = [m for m in matches if m.requirement_type == RequirementType.REQUIRED]
    return SkillScore(
        matches=matches,
        score=sum(m.weighted_credit for m in matches) / total_weight if total_weight else None,
        required_matched=sum(m.credit > 0 for m in required),
        required_total=len(required),
    )
