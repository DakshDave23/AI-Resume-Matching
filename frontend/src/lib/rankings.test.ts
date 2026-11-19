import { describe, expect, it } from "vitest";

import { rankingParams, type RankingRow } from "@/api/rankings";
import { displayName, formatYears, skillChips, summarize, verdictOf } from "@/lib/rankings";

function row(overrides: Partial<RankingRow>): RankingRow {
  return {
    rank: 1,
    resume_id: "r1",
    name: "Asha Rao",
    filename: "asha.pdf",
    current_title: "Engineer",
    total_years: 5,
    relevant_years: 4.5,
    match_percent: 80,
    verdict: "strong",
    skill_score: 0.9,
    semantic_score: 0.8,
    experience_score: 1,
    education_score: 1,
    required_skill_coverage: 1,
    top_matched_skills: [],
    matched_skill_count: 0,
    missing_required_count: 0,
    is_stale: false,
    parse_confidence: 0.9,
    needs_review: false,
    ...overrides,
  };
}

describe("summarize", () => {
  it("averages, picks the top match and counts full required coverage", () => {
    const summary = summarize([
      row({ name: "Asha Rao", match_percent: 91.2 }),
      row({ name: "Ben Ito", match_percent: 70.4, missing_required_count: 2 }),
      row({ name: null, filename: "cv.docx", match_percent: 40.1 }),
    ]);
    expect(summary).toEqual({
      ranked: 3,
      average: 67.2,
      top: { score: 91.2, name: "Asha Rao" },
      meetsAllRequired: 2,
    });
  });

  it("has nothing to say about an empty ranking", () => {
    expect(summarize([])).toEqual({ ranked: 0, average: null, top: null, meetsAllRequired: 0 });
  });
});

it("falls back to the file name when no name was parsed", () => {
  expect(displayName(row({ name: null, filename: "cv.pdf" }))).toBe("cv.pdf");
});

it("formats years", () => {
  expect([formatYears(6.5), formatYears(1), formatYears(null)]).toEqual([
    "6.5 yrs",
    "1.0 yr",
    "Unknown",
  ]);
});

it("names every verdict, and an unknown one", () => {
  expect(["strong", "good", "partial", "weak"].map((v) => verdictOf(v).label)).toEqual([
    "Strong",
    "Good",
    "Partial",
    "Weak",
  ]);
  expect(verdictOf(null).label).toBe("Unscored");
});

it("shows 4 skills, then how many more matched", () => {
  const r = row({
    top_matched_skills: ["Java", "Spring", "SQL", "Docker", "Kafka"],
    matched_skill_count: 9,
  });
  expect(skillChips(r)).toEqual({ names: ["Java", "Spring", "SQL", "Docker"], more: 5 });
  expect(skillChips(row({ top_matched_skills: ["Java"], matched_skill_count: 1 }))).toEqual({
    names: ["Java"],
    more: 0,
  });
});

it("sends only the filters that are set", () => {
  expect(rankingParams({}).toString()).toBe("");
  expect(rankingParams({ search: "  ", minScore: 0, skill: "" }).toString()).toBe("");
  expect(rankingParams({ search: " rao ", minScore: 65, skill: "Spring Boot" }).toString()).toBe(
    "search=rao&min_score=65&skill=Spring+Boot",
  );
});
