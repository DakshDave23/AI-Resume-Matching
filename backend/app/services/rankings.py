"""Re-score a job, change its weights, and export its ranking (design doc §8)."""

import csv
import io
import re
import uuid
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.repositories.rankings import RankingRecord
from app.services.jobs import get_job
from app.services.matching.runner import score_job
from app.services.nlp.embedder import TextEncoder

TOP_SKILLS = 5
FULL_CREDIT_TIERS = ("exact", "alias")
# Spreadsheet apps run a cell starting with one of these as a formula (CSV injection).
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def _lock_scoring(session: Session, job_id: uuid.UUID) -> None:
    """One scoring run per job at a time, across processes; released at commit."""
    key = func.hashtextextended(str(job_id), 0)
    if not session.scalar(select(func.pg_try_advisory_xact_lock(key))):
        raise AppError(409, "Scoring is already running for this job", code="scoring_in_progress")


def rescore(
    session: Session,
    job_id: uuid.UUID,
    encoder: TextEncoder,
    *,
    weights: dict[str, float] | None = None,
) -> int:
    """Score every parsed resume of the job again (saving `weights` first). Commits."""
    job = get_job(session, job_id)
    _lock_scoring(session, job_id)
    if weights is not None:
        job.scoring_weights = weights
        session.flush()
    return score_job(session, job_id, encoder, today=date.today())


# --- Ranking rows ---------------------------------------------------------------------------


def top_matched_skills(matched: list[dict[str, Any]]) -> list[str]:
    """Full-credit skills first, then the rest, in JD order within each group."""
    ordered = sorted(matched, key=lambda m: m["tier"] not in FULL_CREDIT_TIERS)
    return [m["skill"] for m in ordered[:TOP_SKILLS]]


def missing_required_count(missing: list[dict[str, Any]]) -> int:
    return sum(m["requirement_type"] == "required" for m in missing)


def years(months: float | None) -> float | None:
    return round(months / 12, 1) if months is not None else None


# --- CSV export -------------------------------------------------------------------------------

CSV_COLUMNS = [
    "Rank", "Name", "Email", "Phone", "Current title", "Total years", "Relevant years",
    "Match %", "Verdict", "Skills", "Semantic", "Experience", "Education",
    "Required skill coverage", "Matched skills", "Missing skills", "File", "Stale",
]  # fmt: skip


def _cell(value: object) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(_FORMULA_START) else text


def rankings_csv(rows: list[RankingRecord]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for r in rows:
        writer.writerow(
            _cell(value)
            for value in (
                r.rank,
                r.name,
                r.email,
                r.phone,
                r.current_title,
                years(r.total_months),
                years(r.relevant_months),
                r.overall_score,
                r.verdict,
                r.skill_score,
                r.semantic_score,
                r.experience_score,
                r.education_score,
                r.required_skill_coverage,
                "; ".join(m["skill"] for m in r.matched_skills),
                "; ".join(m["skill"] for m in r.missing_skills),
                r.filename,
                "yes" if r.is_stale else "",
            )
        )
    return out.getvalue()


def export_filename(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60] or "job"
    return f"rankings-{slug}.csv"
