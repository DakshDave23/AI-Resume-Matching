import { describe, expect, it } from "vitest";

import type { RankingRow } from "@/api/rankings";
import {
  DEFAULT_WEIGHTS,
  previewScore,
  rerank,
  sameWeights,
  shares,
  toFractions,
  toSliders,
  verdictFor,
} from "@/lib/weights";

function row(id: string, scores: Partial<RankingRow>, rank: number): RankingRow {
  return {
    rank,
    resume_id: id,
    name: id,
    filename: `${id}.pdf`,
    current_title: null,
    total_years: 5,
    relevant_years: 4,
    match_percent: 0,
    verdict: null,
    skill_score: 1,
    semantic_score: 1,
    experience_score: 1,
    education_score: 1,
    required_skill_coverage: 1,
    top_matched_skills: [],
    matched_skill_count: 0,
    missing_required_count: 0,
    is_stale: false,
    parse_confidence: 1,
    needs_review: false,
    ...scores,
  };
}

describe("previewScore", () => {
  it("is the weighted mean of the components x 100", () => {
    const r = row("a", { skill_score: 0.731, semantic_score: 1, experience_score: 1 }, 1);
    // 100 x (0.4 x 0.731 + 0.3 + 0.2 + 0.1) = 89.24
    expect(previewScore(r, DEFAULT_WEIGHTS)).toBe(89.24);
  });

  it("gives an inactive component's weight to the others", () => {
    const r = row("a", { skill_score: 0.5, education_score: null }, 1);
    // (40 x 0.5 + 30 + 20) / 90 x 100
    expect(previewScore(r, DEFAULT_WEIGHTS)).toBe(77.78);
  });

  it("halves education's weight when the JD accepts equivalent experience", () => {
    const r = row("a", { education_score: 0 }, 1);
    expect(previewScore(r, DEFAULT_WEIGHTS)).toBe(90);
    expect(previewScore(r, DEFAULT_WEIGHTS, 0.5)).toBe(94.74); // 90 / 95
  });

  it("scores 0 when every active weight is 0", () => {
    const zero = { skills: 0, semantic: 0, experience: 0, education: 0 };
    expect(previewScore(row("a", {}, 1), zero)).toBe(0);
  });
});

describe("rerank", () => {
  const stuffer = row("stuffer", { skill_score: 1, semantic_score: 0.2, experience_score: 0 }, 2);
  const engineer = row("engineer", { skill_score: 0.6, semantic_score: 1, experience_score: 1 }, 1);

  it("changes the order when the weights change, and keeps the saved rank", () => {
    const skillsOnly = { skills: 100, semantic: 0, experience: 0, education: 0 };
    const ranked = rerank([engineer, stuffer], skillsOnly);
    expect(ranked.map((r) => [r.resume_id, r.rank, r.previous_rank, r.match_percent])).toEqual([
      ["stuffer", 1, 2, 100],
      ["engineer", 2, 1, 60],
    ]);
    expect(ranked[0]?.verdict).toBe("strong");
  });

  it("breaks ties by required coverage, then relevant experience", () => {
    const a = row("a", { required_skill_coverage: 0.5 }, 1);
    const b = row("b", { required_skill_coverage: 1 }, 2);
    const c = row("c", { required_skill_coverage: 1, relevant_years: 9 }, 3);
    expect(rerank([a, b, c], DEFAULT_WEIGHTS).map((r) => r.resume_id)).toEqual(["c", "b", "a"]);
  });
});

it("converts between saved fractions and slider values", () => {
  expect(toSliders({ skills: 0.4, semantic: 0.3, experience: 0.2, education: 0.1 })).toEqual(
    DEFAULT_WEIGHTS,
  );
  expect(toSliders({ skills: 2, semantic: 2, experience: 0, education: 0 })).toEqual({
    skills: 50,
    semantic: 50,
    experience: 0,
    education: 0,
  });
  expect(toFractions(DEFAULT_WEIGHTS)).toEqual({
    skills: 0.4,
    semantic: 0.3,
    experience: 0.2,
    education: 0.1,
  });
});

it("compares weights by their shares", () => {
  expect(shares({ skills: 2, semantic: 1, experience: 1, education: 0 }).skills).toBe(0.5);
  expect(
    sameWeights(DEFAULT_WEIGHTS, { skills: 80, semantic: 60, experience: 40, education: 20 }),
  ).toBe(true);
  expect(sameWeights(DEFAULT_WEIGHTS, { ...DEFAULT_WEIGHTS, education: 0 })).toBe(false);
});

it("names the verdict band", () => {
  expect([80, 79.99, 65, 50, 49.9].map(verdictFor)).toEqual([
    "strong",
    "good",
    "good",
    "partial",
    "weak",
  ]);
});
