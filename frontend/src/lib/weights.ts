/**
 * Preview a ranking under new weights from the stored component scores, without the API
 * (design doc §8: "the UI previews the new ranking instantly ... then PATCH /weights saves it").
 *
 * This mirrors the backend's `combine` (app/services/matching/scorer.py) and `assign_ranks`
 * (app/repositories/matches.py): the weighted mean of the active components x 100, with
 * education's weight halved when the JD accepts equivalent experience, ranked by score, then
 * required-skill coverage, then relevant experience. Stored components have 3 decimals, so
 * a preview can differ from a saved score by a few hundredths of a point.
 */
import type { RankingRow } from "@/api/rankings";

export const COMPONENTS = ["skills", "semantic", "experience", "education"] as const;
export type Component = (typeof COMPONENTS)[number];
export type Weights = Record<Component, number>;

export const COMPONENT_LABELS: Record<Component, string> = {
  skills: "Skills",
  semantic: "Semantic similarity",
  experience: "Relevant experience",
  education: "Education",
};

/** The design doc's defaults (§6.1), as slider values out of 100. */
export const DEFAULT_WEIGHTS: Weights = { skills: 40, semantic: 30, experience: 20, education: 10 };

/** Education's weight factor when the JD accepts equivalent experience (scoring_config). */
export const EQUIVALENT_EXPERIENCE_FACTOR = 0.5;

/** Verdict bands (§7): 80+ strong, 65+ good, 50+ partial, else weak. */
const VERDICT_BANDS: [number, string][] = [
  [80, "strong"],
  [65, "good"],
  [50, "partial"],
  [0, "weak"],
];

const SCORE_FIELD: Record<Component, keyof RankingRow> = {
  skills: "skill_score",
  semantic: "semantic_score",
  experience: "experience_score",
  education: "education_score",
};

/** The job's saved weights (fractions such as 0.4) as slider values out of 100. */
export function toSliders(saved: Record<string, number>): Weights {
  const total = COMPONENTS.reduce((sum, c) => sum + (saved[c] ?? 0), 0);
  if (total <= 0) return { ...DEFAULT_WEIGHTS };
  return Object.fromEntries(
    COMPONENTS.map((c) => [c, Math.round(((saved[c] ?? 0) / total) * 100)]),
  ) as Weights;
}

/** What PATCH /weights takes: the slider values as fractions. */
export function toFractions(weights: Weights): Weights {
  return Object.fromEntries(COMPONENTS.map((c) => [c, weights[c] / 100])) as Weights;
}

/** Each weight's share of the total, 0–1. All zero gives all zero. */
export function shares(weights: Weights): Weights {
  const total = COMPONENTS.reduce((sum, c) => sum + weights[c], 0);
  return Object.fromEntries(
    COMPONENTS.map((c) => [c, total > 0 ? weights[c] / total : 0]),
  ) as Weights;
}

export function sameWeights(a: Weights, b: Weights): boolean {
  const [x, y] = [shares(a), shares(b)];
  return COMPONENTS.every((c) => Math.abs(x[c] - y[c]) < 1e-9);
}

export function verdictFor(score: number): string {
  return VERDICT_BANDS.find(([low]) => score >= low)?.[1] ?? "weak";
}

/** One candidate's match % under `weights`, rounded as stored (2 decimals). */
export function previewScore(row: RankingRow, weights: Weights, educationFactor = 1): number {
  const raw = { ...weights, education: weights.education * educationFactor };
  const active = COMPONENTS.filter((c) => row[SCORE_FIELD[c]] !== null);
  const total = active.reduce((sum, c) => sum + raw[c], 0);
  if (total <= 0) return 0;
  const score =
    (100 * active.reduce((sum, c) => sum + raw[c] * (row[SCORE_FIELD[c]] as number), 0)) / total;
  return Math.round(Math.min(100, Math.max(0, score)) * 100) / 100;
}

export type PreviewRow = RankingRow & { previous_rank: number | null };

function byRank(a: RankingRow, b: RankingRow): number {
  return (
    b.match_percent - a.match_percent ||
    (b.required_skill_coverage ?? -1) - (a.required_skill_coverage ?? -1) ||
    (b.relevant_years ?? -1) - (a.relevant_years ?? -1) ||
    a.resume_id.localeCompare(b.resume_id)
  );
}

/** Every row re-scored and re-ranked under `weights`, best first; `previous_rank` is the saved one. */
export function rerank(rows: RankingRow[], weights: Weights, educationFactor = 1): PreviewRow[] {
  return rows
    .map((row) => {
      const score = previewScore(row, weights, educationFactor);
      return { ...row, match_percent: score, verdict: verdictFor(score), previous_rank: row.rank };
    })
    .sort(byRank)
    .map((row, i) => ({ ...row, rank: i + 1 }));
}
