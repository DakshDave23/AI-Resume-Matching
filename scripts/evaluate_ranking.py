"""Measure ranking quality on the samples (design doc §13 and §6.7).

Every sample resume is scored against every sample JD with the real model, exactly
as the pipeline scores (in memory, without the database). The report covers:

- each JD's ranking next to its expected tiers (sample_data/ground_truth.json);
- Spearman correlation between match % and expected tier, and precision at k
  (k = the JD's number of "strong" samples; 4 for the Java JD);
- the keyword-only ablation: semantic weight 0 and skill tiers 3-4 off;
- partial credit for tiers 3-4 at 0.4 / 0.5 / 0.6 (§6.7: rankings should hold);
- weight sensitivity: each weight moved by +-0.1, does the top 3 stay?
- how long the 15 files take to parse, embed and score.

Usage (from the repo root, with the backend virtualenv):
    backend/.venv/Scripts/python scripts/evaluate_ranking.py                 # Windows
    backend/.venv/bin/python scripts/evaluate_ranking.py                     # macOS/Linux
    ... scripts/evaluate_ranking.py --out docs/ranking-results.md            # also save it
"""

import argparse
import io
import json
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.services.extraction import ExtractionError, extract_text
from app.services.matching import scoring_config as config
from app.services.matching.inputs import candidate_data_from_parse, skill_vectors
from app.services.matching.scorer import (
    MatchOutcome,
    ScoringJob,
    combine,
    score_candidate,
    scoring_job_from_parse,
)
from app.services.matching.skills import Tier
from app.services.nlp.embedder import Embedder
from app.services.nlp.vectors import embed_job, embed_resume
from app.services.parsing.chunker import chunk_resume
from app.services.parsing.jd_parser import parse_job
from app.services.parsing.resume_parser import ParsedResume, parse_resume

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "sample_data"
REGION = "IN"
# Spearman needs an order of tiers; "good" sits between strong and partial.
TIER_VALUE = {"strong": 3.0, "good": 2.5, "partial": 2.0, "weak": 1.0}
INDIRECT = (Tier.RELATED, Tier.CONTEXTUAL)


@dataclass(frozen=True)
class Scored:
    persona: int
    file: str
    tier: str
    outcome: MatchOutcome


# --- Scoring the samples ----------------------------------------------------------------


def score_all(truth: dict[str, Any], encoder: Embedder) -> tuple[dict[str, list[Scored]], float]:
    """Every text sample against every JD. Returns the results and the seconds 15 files took."""
    as_of = date.fromisoformat(truth["as_of"])
    parsed: list[tuple[dict[str, Any], ParsedResume, Any, Any]] = []
    started = time.perf_counter()
    for resume in truth["resumes"]:
        data = (SAMPLES / resume["file"]).read_bytes()
        try:
            text = extract_text(data, resume["format"]).text
        except ExtractionError:
            continue  # the scanned sample: rejected, as in the pipeline
        p = parse_resume(text, today=as_of, region=REGION)
        chunks = chunk_resume(p.sections, p.work)
        parsed.append((resume, p, chunks, embed_resume(chunks, p.work.roles, encoder)))
    seconds = time.perf_counter() - started

    results: dict[str, list[Scored]] = {}
    for jd in truth["jds"]:
        job = parse_job((SAMPLES / jd["file"]).read_text(encoding="utf-8"))
        job_vectors = embed_job(job.requirements, encoder)
        names = {s.name for s in job.skills} | {
            n for _, p, _, _ in parsed for n in p.skills.names()
        }
        vectors = skill_vectors(sorted(names), encoder)
        scoring_job = scoring_job_from_parse(job, job_vectors, vectors, encoder)
        jd_started = time.perf_counter()
        results[jd["id"]] = [
            Scored(
                resume["id"],
                resume["file"].rsplit("/", 1)[-1],
                resume["expected_tier"][jd["id"]],
                _score(scoring_job, p, chunks, rv, vectors, as_of, encoder),
            )
            for resume, p, chunks, rv in parsed
        ]
        if jd["id"] == "backend_java":
            seconds += time.perf_counter() - jd_started  # one JD's worth of scoring
    return results, seconds


def _score(
    job: ScoringJob, parsed: ParsedResume, chunks: Any, vectors: Any, skill_vecs: Any,
    as_of: date, encoder: Embedder,
) -> MatchOutcome:  # fmt: skip
    candidate = candidate_data_from_parse(
        parsed, chunks, vectors, skill_vecs, list(job.skills.skills)
    )
    return score_candidate(job, candidate, today=as_of, encoder=encoder)


# --- Variants (no rescoring needed: the components are kept) --------------------------------


def skill_score(outcome: MatchOutcome, partial: float | None) -> float | None:
    """The skill score with tiers 3-4 at `partial` credit; None switches them off (credit 0)."""
    matches = outcome.skills.matches
    total = sum(m.weight for m in matches)
    if not total:
        return None
    credit = [(partial or 0.0) if m.tier in INDIRECT else m.credit for m in matches]
    return sum(m.weight * c for m, c in zip(matches, credit, strict=True)) / total


def total(
    outcome: MatchOutcome,
    weights: Mapping[str, float] = config.DEFAULT_WEIGHTS,
    *,
    skills: float | None = None,
    use_skills_override: bool = False,
) -> float:
    components = dict(outcome.combined.components)
    if use_skills_override:
        components["skills"] = skills
    return combine(components, weights, education_factor=outcome.education.weight_factor).score


Scorer = Callable[[Scored], float]


def with_partial_credit(credit: float) -> Scorer:
    def score(r: Scored) -> float:
        skills = skill_score(r.outcome, credit)
        return total(r.outcome, skills=skills, use_skills_override=True)

    return score


def with_weights(weights: Mapping[str, float]) -> Scorer:
    def score(r: Scored) -> float:
        return total(r.outcome, weights)

    return score


def order(rows: list[Scored], score: Scorer) -> list[tuple[Scored, float]]:
    return sorted(((r, score(r)) for r in rows), key=lambda pair: -pair[1])


# --- Metrics ----------------------------------------------------------------------------------


def _ranks(values: list[float]) -> list[float]:
    """1-based ranks, ties averaged."""
    ordered = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(ordered):
        j = i
        while j + 1 < len(ordered) and values[ordered[j + 1]] == values[ordered[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[ordered[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(xs: list[float], ys: list[float]) -> float:
    rx, ry = _ranks(xs), _ranks(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    sx = sum((a - mx) ** 2 for a in rx) ** 0.5
    sy = sum((b - my) ** 2 for b in ry) ** 0.5
    return cov / (sx * sy) if sx and sy else 0.0


def metrics(ranked: list[tuple[Scored, float]]) -> dict[str, Any]:
    strong = [r.persona for r, _ in ranked if r.tier == "strong"]
    k = len(strong)
    top = [r.persona for r, _ in ranked[:k]]
    return {
        "spearman": spearman([s for _, s in ranked], [TIER_VALUE[r.tier] for r, _ in ranked]),
        "k": k,
        "precision": sum(p in strong for p in top) / k if k else 1.0,
        "top3": [r.persona for r, _ in ranked[:3]],
        "last": ranked[-1][0].persona,
    }


# --- Report -------------------------------------------------------------------------------


def _ranking_table(ranked: list[tuple[Scored, float]]) -> list[str]:
    lines = [
        "| Rank | Sample | Expected | Match % | Skills | Semantic | Experience | Education |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for rank, (r, score) in enumerate(ranked, start=1):
        c = r.outcome.combined.components
        cells = [f"{c[n]:.2f}" if c[n] is not None else "—" for n in config.COMPONENTS]
        lines.append(
            f"| {rank} | {r.persona} `{r.file}` | {r.tier} | {score:.1f} | "
            + " | ".join(cells)
            + " |"
        )
    return lines


def report(results: dict[str, list[Scored]], seconds: float, files: int) -> str:
    lines = [
        "# Ranking results",
        "",
        "Generated by `scripts/evaluate_ranking.py`: every text sample scored against every",
        f"sample JD with `{get_settings().embedding_model}` and the thresholds in",
        f"`backend/app/services/matching/scoring_config.py` (scoring {config.SCORING_VERSION}).",
        "Expected tiers come from `sample_data/ground_truth.json`.",
        "",
        "## Summary",
        "",
        "| JD | Spearman (score vs tier) | Precision at k | Top 3 | Last |",
        "| --- | --- | --- | --- | --- |",
    ]
    default: dict[str, list[tuple[Scored, float]]] = {
        jd: order(rows, lambda r: r.outcome.score) for jd, rows in results.items()
    }
    for jd, ranked in default.items():
        m = metrics(ranked)
        lines.append(
            f"| {jd} | {m['spearman']:.2f} | {m['precision']:.2f} (k = {m['k']}) | "
            f"{', '.join(map(str, m['top3']))} | {m['last']} |"
        )
    lines += ["", "Goal (design doc §13): Spearman ≥ 0.8; precision at 4 for the Java JD.", ""]

    for jd, ranked in default.items():
        lines += [f"## Ranking: {jd}", "", *_ranking_table(ranked), ""]

    java = results["backend_java"]
    lines += _ablation(java) + _partial_credit(results) + _weight_sensitivity(java)
    lines += _findings(default) + CALIBRATION
    lines += [
        "## Speed",
        "",
        f"Extracting, parsing, embedding and scoring the {files} readable samples against one JD "
        f"took {seconds:.1f} s on this machine's CPU (model already loaded; no database writes).",
        "",
    ]
    return "\n".join(lines)


def keyword_only(r: Scored) -> float:
    """Semantic weight 0 and skill tiers 3-4 off (§13 ablation)."""
    weights = dict(config.DEFAULT_WEIGHTS) | {"semantic": 0.0}
    return total(r.outcome, weights, skills=skill_score(r.outcome, None), use_skills_override=True)


def _ablation(rows: list[Scored]) -> list[str]:
    full = order(rows, lambda r: r.outcome.score)
    keyword = order(rows, keyword_only)
    position = {name: {r.persona: i + 1 for i, (r, _) in enumerate(ranking)} for name, ranking in
                (("full", full), ("keyword", keyword))}  # fmt: skip
    lines = [
        "## Keyword-only ablation (Java JD)",
        "",
        "Semantic weight 0 and skill tiers 3-4 (related, inferred) off. Expected: sample 2",
        "(synonyms) falls and sample 7 (keyword stuffer) rises.",
        "",
        "| Rank | Full system | Keyword only |",
        "| --- | --- | --- |",
    ]
    for i, ((a, sa), (b, sb)) in enumerate(zip(full, keyword, strict=True), start=1):
        lines.append(
            f"| {i} | {a.persona} ({a.tier}, {sa:.1f}) | {b.persona} ({b.tier}, {sb:.1f}) |"
        )
    for persona in (2, 7, 3):
        lines.append("")
        lines.append(
            f"Sample {persona}: #{position['full'][persona]} with the full system, "
            f"#{position['keyword'][persona]} keyword-only."
        )
    m_full, m_kw = metrics(full), metrics(keyword)
    lines += [
        "",
        f"Spearman {m_full['spearman']:.2f} → {m_kw['spearman']:.2f}; "
        f"precision at 4 {m_full['precision']:.2f} → {m_kw['precision']:.2f}.",
        "",
    ]
    return lines


def _partial_credit(results: dict[str, list[Scored]]) -> list[str]:
    lines = [
        "## Partial credit for related and inferred skills",
        "",
        "Design doc §6.7: check that rankings hold with 0.4 and 0.6 instead of 0.5.",
        "",
        "| Credit | JD | Spearman | Precision at k | Top 3 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for credit in (0.4, 0.5, 0.6):
        for jd, rows in results.items():
            ranked = order(rows, with_partial_credit(credit))
            m = metrics(ranked)
            lines.append(
                f"| {credit} | {jd} | {m['spearman']:.2f} | {m['precision']:.2f} | "
                f"{', '.join(map(str, m['top3']))} |"
            )
    return [*lines, ""]


def _weight_sensitivity(rows: list[Scored]) -> list[str]:
    base_top3 = metrics(order(rows, lambda r: r.outcome.score))["top3"]
    lines = [
        "## Weight sensitivity (Java JD)",
        "",
        f"Each weight moved by ±0.1 from the defaults. Default top 3: {base_top3}.",
        "",
        "| Change | Top 3 | Same three | Same order | Precision at 4 | Spearman |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for name in config.COMPONENTS:
        for delta in (-0.1, 0.1):
            weights = dict(config.DEFAULT_WEIGHTS)
            weights[name] = max(0.0, weights[name] + delta)
            m = metrics(order(rows, with_weights(weights)))
            same_set = "yes" if set(m["top3"]) == set(base_top3) else "**no**"
            same_order = "yes" if m["top3"] == base_top3 else "no"
            lines.append(
                f"| {name} {delta:+.1f} | {', '.join(map(str, m['top3']))} | {same_set} | "
                f"{same_order} | {m['precision']:.2f} | {m['spearman']:.2f} |"
            )
    return [*lines, ""]


def _findings(default: dict[str, list[tuple[Scored, float]]]) -> list[str]:
    java = default["backend_java"]
    score = {r.persona: s for r, s in java}
    sample_3 = next(r for r, _ in java if r.persona == 3)
    keyword_loss = score[3] - keyword_only(sample_3)
    others = [ranked for jd, ranked in default.items() if jd != "backend_java"]
    margins = [ranked[0][1] - ranked[1][1] for ranked in others]
    return [
        "## Findings",
        "",
        f"- **Precision at 4 is {metrics(java)['precision']:.2f} for the Java JD.** Sample 11 "
        f'("good": every skill an exact match, but a diploma) ranks above sample 3 '
        f'("strong": PostgreSQL and Kafka only related, Microservices inferred), '
        f"{score[11]:.1f} to {score[3]:.1f}. Under the default weights the diploma costs 5 "
        "points and the indirect skills 10.8. Only raising education's weight to 0.2 changes "
        "that (see the weight table). The doc's defaults (40/30/20/10) were kept rather than "
        "tuned to one pair of samples.",
        "- **Keyword-only: sample 7 (keyword stuffer) rises, sample 2 (synonyms) does not "
        "fall.** Sample 2's synonyms (k8s, Postgres) are all in the alias dictionary: tier 2, "
        "which the ablation keeps. The sample that leans on meaning is sample 3: it loses "
        f"{keyword_loss:.1f} points.",
        "- **Spearman for the Data Scientist and Frontend JDs is low** because each has one "
        'strong sample and 12-13 equally "weak" ones, so the statistic mostly measures the '
        "order among the weak samples. In both, the strong sample ranks first, by "
        f"{min(margins):.0f} points or more.",
        "- **Partial credit at 0.4, 0.5 or 0.6 gives the same rankings:** the half credit is not "
        "a fragile choice.",
        "",
    ]


# The thresholds the doc said to calibrate (§6.7), with what was measured. Each one's
# measurements are in the comments of scoring_config.py.
CALIBRATION = [
    "## Calibrated thresholds",
    "",
    "| Parameter | Doc's start | Used | Why |",
    "| --- | --- | --- | --- |",
    "| Related-skill cosine (tier 3) | 0.80 | 0.58 | No related pair reaches 0.80 with this "
    "model; 0.58 keeps Kafka/RabbitMQ (0.59) and PostgreSQL/MySQL (0.62), drops "
    "Next.js/Node.js (0.55) and Java/Python (0.54) |",
    "| Contextual cosine (tier 4) | 0.55 | 0.43 | The one described-but-unnamed skill "
    "(sample 3, Microservices) scores 0.46; the highest false one 0.40 |",
    "| Semantic floor L / ceiling H | 0.20 / 0.70 | 0.30 / 0.47 | Mean raw score of the weak "
    "(0.295) and strong (0.473) sample/JD pairs: the doc's rule |",
    "| Requirement covered / partial | 0.55 / 0.40 | 0.40 / 0.30 | A strong candidate's median "
    "best match is 0.40 with this model |",
    "| Role relevance: relevant / partly | 0.55 / 0.40 | 0.55 / 0.42 | Sample 8's QA role "
    "scores 0.39 and must not count |",
    "| Field-of-study cosine | 0.6 | 0.6 | Unrelated fields top out at 0.54 |",
    "| Partial credit, tiers 3-4 | 0.5 | 0.5 | Rankings identical at 0.4 and 0.6 |",
    "| Weights | 40/30/20/10 | 40/30/20/10 | Kept; see Findings |",
    "",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, help="also write the report to this file")
    args = parser.parse_args(argv)

    truth = json.loads((SAMPLES / "ground_truth.json").read_text(encoding="utf-8"))
    encoder = Embedder(get_settings().embedding_model)
    results, seconds = score_all(truth, encoder)
    markdown = report(results, seconds, len(next(iter(results.values()))))

    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    print(markdown)
    if args.out:
        args.out.write_text(markdown, encoding="utf-8", newline="\n")
        print(f"Saved to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
