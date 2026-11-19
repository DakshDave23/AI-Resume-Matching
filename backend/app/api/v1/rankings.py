"""Scoring, rankings, candidate detail, weights and export routes (design doc §8)."""

import uuid
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_embedder
from app.core.database import get_db
from app.core.errors import AppError
from app.repositories import rankings as ranking_repo
from app.repositories.skills import find_skill
from app.schemas.rankings import (
    CandidateOut,
    EducationOut,
    ExplanationOut,
    MatchedSkillOut,
    MatchRequest,
    MatchRunOut,
    MissingSkillOut,
    RankingRow,
    RankingSort,
    RankingsOut,
    RequirementMatchOut,
    UnrankedOut,
    Weights,
    WeightsOut,
)
from app.services import rankings as ranking_service
from app.services.jobs import get_job
from app.services.nlp.embedder import TextEncoder
from app.services.parsing.resume_parser import MIN_CONFIDENCE

router = APIRouter(prefix="/jobs", tags=["rankings"])

Responses = dict[int | str, dict[str, Any]]
MODEL_LOADING: Responses = {503: {"description": "The embedding model is still loading"}}
NOT_FOUND: Responses = {404: {"description": "No such job"}}
BUSY: Responses = {409: {"description": "Scoring is already running"}}


def _float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _needs_review(confidence: Decimal | None) -> bool:
    """Low parse confidence: the parse may have missed things (as in the upload status)."""
    return confidence is not None and confidence < Decimal(str(MIN_CONFIDENCE))


@router.post(
    "/{job_id}/match",
    response_model=MatchRunOut,
    summary="Re-score every parsed resume of the job",
    description="Optionally saves new `weights` first. Rescoring replaces earlier results.",
    responses={**NOT_FOUND, **BUSY, **MODEL_LOADING},
)
def run_match(
    job_id: uuid.UUID,
    body: Annotated[MatchRequest | None, Body()] = None,
    db: Session = Depends(get_db),
    encoder: TextEncoder = Depends(get_embedder),
) -> MatchRunOut:
    weights = body.weights.model_dump() if body and body.weights else None
    scored = ranking_service.rescore(db, job_id, encoder, weights=weights)
    return MatchRunOut(job_id=job_id, scored=scored, weights=get_job(db, job_id).scoring_weights)


@router.patch(
    "/{job_id}/weights",
    response_model=WeightsOut,
    summary="Save scoring weights and recompute the totals",
    responses={**NOT_FOUND, **BUSY, **MODEL_LOADING},
)
def update_weights(
    job_id: uuid.UUID,
    body: Weights,
    db: Session = Depends(get_db),
    encoder: TextEncoder = Depends(get_embedder),
) -> WeightsOut:
    scored = ranking_service.rescore(db, job_id, encoder, weights=body.model_dump())
    return WeightsOut(job_id=job_id, weights=get_job(db, job_id).scoring_weights, scored=scored)


def _rows(
    db: Session,
    job_id: uuid.UUID,
    min_score: float | None,
    skill: str | None,
    search: str | None,
    sort: RankingSort,
) -> list[ranking_repo.RankingRecord]:
    get_job(db, job_id)  # 404 for an unknown job
    canonical = None
    if skill:
        found = find_skill(db, skill)  # "k8s" filters by Kubernetes
        if found is None:
            return []
        canonical = found.canonical_name
    return ranking_repo.rankings(
        db, job_id, min_score=min_score, skill=canonical, search=search, sort=sort
    )


Filters = {
    "min_score": Query(ge=0, le=100, description="Only matches at or above this %"),
    "skill": Query(max_length=100, description="Only candidates matching this skill"),
    "search": Query(max_length=100, description="Name, file name or current title"),
}


@router.get(
    "/{job_id}/rankings",
    response_model=RankingsOut,
    summary="The job's ranked candidates (dashboard rows)",
    responses=NOT_FOUND,
)
def get_rankings(
    job_id: uuid.UUID,
    min_score: Annotated[float | None, Filters["min_score"]] = None,
    skill: Annotated[str | None, Filters["skill"]] = None,
    search: Annotated[str | None, Filters["search"]] = None,
    sort: RankingSort = "score",
    db: Session = Depends(get_db),
) -> RankingsOut:
    rows = _rows(db, job_id, min_score, skill, search, sort)
    return RankingsOut(
        job_id=job_id,
        total=len(rows),
        rows=[
            RankingRow(
                rank=r.rank,
                resume_id=r.resume_id,
                name=r.name,
                filename=r.filename,
                current_title=r.current_title,
                total_years=ranking_service.years(r.total_months),
                relevant_years=ranking_service.years(r.relevant_months),
                match_percent=float(r.overall_score),
                verdict=r.verdict,
                skill_score=_float(r.skill_score),
                semantic_score=_float(r.semantic_score),
                experience_score=_float(r.experience_score),
                education_score=_float(r.education_score),
                required_skill_coverage=_float(r.required_skill_coverage),
                top_matched_skills=ranking_service.top_matched_skills(r.matched_skills),
                matched_skill_count=len(r.matched_skills),
                missing_required_count=ranking_service.missing_required_count(r.missing_skills),
                is_stale=r.is_stale,
                parse_confidence=_float(r.parse_confidence),
                needs_review=_needs_review(r.parse_confidence),
            )
            for r in rows
        ],
        not_ranked=[
            UnrankedOut(
                resume_id=r.id,
                filename=r.original_filename,
                parse_status=r.parse_status,
                parse_error=r.parse_error,
            )
            for r in ranking_repo.unranked_resumes(db, job_id)
        ],
    )


@router.get(
    "/{job_id}/rankings/export",
    summary="The ranking as a CSV file (same filters as the rankings)",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}}, **NOT_FOUND},
)
def export_rankings(
    job_id: uuid.UUID,
    min_score: Annotated[float | None, Filters["min_score"]] = None,
    skill: Annotated[str | None, Filters["skill"]] = None,
    search: Annotated[str | None, Filters["search"]] = None,
    sort: RankingSort = "score",
    db: Session = Depends(get_db),
) -> Response:
    rows = _rows(db, job_id, min_score, skill, search, sort)
    filename = ranking_service.export_filename(get_job(db, job_id).title)
    return Response(
        content=ranking_service.rankings_csv(rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/{job_id}/candidates/{resume_id}",
    response_model=CandidateOut,
    summary="Full candidate analysis, as stored when scored",
    responses={404: {"description": "No such job, or this resume has no score for it"}},
)
def get_candidate(
    job_id: uuid.UUID, resume_id: uuid.UUID, db: Session = Depends(get_db)
) -> CandidateOut:
    found = ranking_repo.candidate_match(db, job_id, resume_id)
    if found is None:
        raise AppError(404, "No scored candidate with this id for this job")
    match, resume, person = found
    explanation = ExplanationOut.model_validate(match.explanation)
    relevant = explanation.details.experience.relevant_months
    return CandidateOut(
        job_id=job_id,
        resume_id=resume_id,
        rank=match.rank,
        match_percent=float(match.overall_score),
        is_stale=match.is_stale,
        scoring_version=match.scoring_version,
        weights_used=match.weights_used,
        name=person.full_name if person else None,
        email=person.email if person else None,
        phone=person.phone if person else None,
        location=person.location if person else None,
        linkedin_url=person.linkedin_url if person else None,
        github_url=person.github_url if person else None,
        filename=resume.original_filename,
        current_title=resume.current_title,
        total_years=ranking_service.years(resume.total_experience_months),
        relevant_years=ranking_service.years(relevant),
        parse_confidence=_float(resume.parse_confidence),
        needs_review=_needs_review(resume.parse_confidence),
        educations=[
            EducationOut(
                degree=e.degree_raw,
                degree_level=e.degree_level,
                field_of_study=e.field_of_study,
                institution=e.institution,
                graduation_year=e.graduation_year,
            )
            for e in ranking_repo.resume_educations(db, resume_id)
        ],
        raw_text=resume.raw_text,
        component_scores={
            "skills": _float(match.skill_score),
            "semantic": _float(match.semantic_score),
            "experience": _float(match.experience_score),
            "education": _float(match.education_score),
        },
        required_skill_coverage=_float(match.required_skill_coverage),
        matched_skills=[MatchedSkillOut.model_validate(m) for m in match.matched_skills],
        missing_skills=[MissingSkillOut.model_validate(m) for m in match.missing_skills],
        requirement_matches=[
            RequirementMatchOut.model_validate(m) for m in match.requirement_matches
        ],
        explanation=explanation,
    )
