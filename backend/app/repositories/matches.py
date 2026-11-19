"""Store match results and rank them within a job (design doc §4 and §6.1).

Rescoring upserts on (job_id, resume_id), so it is always safe to run again.
Ranks are assigned in SQL over every scored resume of the job, so a new batch
slots in among the earlier ones.
"""

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import MatchResult
from app.services.matching import scoring_config as config
from app.services.matching.explainer import explain
from app.services.matching.scorer import MatchOutcome
from app.services.matching.skills import Tier


def _score(value: float | None, places: int = 3) -> Decimal | None:
    return Decimal(str(round(value, places))) if value is not None else None


def match_json(outcome: MatchOutcome) -> dict[str, Any]:
    """The JSONB columns: what the candidate view and the explanation read back."""
    skills, semantic = outcome.skills, outcome.semantic
    experience, education = outcome.experience, outcome.education
    matched = [
        {
            "skill": m.name,
            "requirement_type": m.requirement_type.value,
            "weight": m.weight,
            "tier": m.tier.value,
            "credit": round(m.credit, 3),
            "matched_skill": m.matched_skill,
            "similarity": m.similarity,
            "evidence": m.evidence,
            "min_years": m.min_years,
            "years_used": m.years_used,
        }
        for m in skills.matches
        if m.tier != Tier.MISSING
    ]
    missing = [
        {"skill": m.name, "requirement_type": m.requirement_type.value, "weight": m.weight}
        for m in skills.matches
        if m.tier == Tier.MISSING
    ]
    requirements = [
        {
            "requirement_id": m.requirement_id,
            "text": m.text,
            "requirement_type": m.requirement_type.value,
            "similarity": m.similarity,
            "status": m.status.value,
            "evidence": m.evidence,
            "evidence_section": m.evidence_section,
        }
        for m in (semantic.matches if semantic else ())
    ]
    details = {
        "components": outcome.combined.components,
        "effective_weights": outcome.combined.effective_weights,
        "skills": {
            "required_matched": skills.required_matched,
            "required_total": skills.required_total,
        },
        "semantic": (
            {
                "coverage": round(semantic.coverage, 3),
                "document_similarity": round(semantic.document_similarity, 3),
                "raw": round(semantic.raw, 3),
            }
            if semantic
            else None
        ),
        "experience": {
            "relevant_months": round(experience.relevant_months, 1),
            "total_months": experience.total_months,
            "min_years": experience.min_years,
            "max_years": experience.max_years,
            "above_max": experience.above_max,
            "roles": [
                {
                    "title": r.title,
                    "company": r.company,
                    "start": r.start.isoformat() if r.start else None,
                    "end": r.end.isoformat() if r.end else None,
                    "months": r.months,
                    "similarity": r.similarity,
                    "factor": r.factor,
                    "counted": r.counted,
                }
                for r in experience.roles
            ],
        },
        "education": {
            "required_level": education.required_level,
            "candidate_level": education.candidate_level,
            "level_score": education.level_score,
            "required_fields": list(education.required_fields),
            "field_result": education.field_result.value,
            "candidate_field": education.candidate_field,
            "matched_field": education.matched_field,
            "weight_factor": education.weight_factor,
            "waived_by_experience": education.waived_by_experience,
        },
    }
    return {
        "matched_skills": matched,
        "missing_skills": missing,
        "requirement_matches": requirements,
        "details": details,
    }


def upsert_match(
    session: Session, job_id: uuid.UUID, resume_id: uuid.UUID, outcome: MatchOutcome
) -> None:
    """Insert or replace the job/resume pair's result. The rank is set by `assign_ranks`."""
    data = match_json(outcome)
    components = outcome.combined.components
    values = {
        "job_id": job_id,
        "resume_id": resume_id,
        "overall_score": _score(outcome.score, 2),
        "skill_score": _score(components["skills"]),
        "semantic_score": _score(components["semantic"]),
        "experience_score": _score(components["experience"]),
        "education_score": _score(components["education"]),
        "required_skill_coverage": _score(outcome.skills.required_coverage),
        "relevant_experience_months": round(outcome.experience.relevant_months),
        "matched_skills": data["matched_skills"],
        "missing_skills": data["missing_skills"],
        "requirement_matches": data["requirement_matches"],
        "explanation": explain(outcome) | {"details": data["details"]},
        "weights_used": outcome.weights,
        "scoring_version": config.SCORING_VERSION,
        "rank": None,
        "is_stale": False,
        "computed_at": func.now(),
    }
    statement = insert(MatchResult).values(values)
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[MatchResult.job_id, MatchResult.resume_id],
            set_={k: statement.excluded[k] for k in values if k not in ("job_id", "resume_id")},
        )
    )


def assign_ranks(session: Session, job_id: uuid.UUID) -> None:
    """1..n by score; ties by required-skill coverage, then relevant experience (§6.1)."""
    ranked = (
        select(
            MatchResult.id,
            func.row_number()
            .over(
                order_by=(
                    MatchResult.overall_score.desc(),
                    MatchResult.required_skill_coverage.desc().nulls_last(),
                    MatchResult.relevant_experience_months.desc().nulls_last(),
                    MatchResult.resume_id,  # last resort: stable, never random
                )
            )
            .label("position"),
        )
        .where(MatchResult.job_id == job_id)
        .subquery()
    )
    session.execute(
        update(MatchResult)
        .where(MatchResult.id == ranked.c.id)
        .values(rank=ranked.c.position)
        .execution_options(synchronize_session=False)
    )
