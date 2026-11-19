import { describe, expect, it } from "vitest";

import {
  degreeName,
  formatPoints,
  highlight,
  neighbours,
  relevanceLabel,
  roleDates,
  TIERS,
} from "@/lib/candidate";

describe("highlight", () => {
  const marked = (text: string, terms: string[]) =>
    highlight(text, terms)
      .filter((s) => s.match)
      .map((s) => s.text);

  it("marks whole words in any case and keeps every character", () => {
    const text = "Built REST APIs in java; JavaScript on the side.";
    expect(marked(text, ["Java", "REST APIs"])).toEqual(["REST APIs", "java"]);
    expect(
      highlight(text, ["Java"])
        .map((s) => s.text)
        .join(""),
    ).toBe(text);
  });

  it("prefers the longer term and handles symbols", () => {
    expect(marked("Spring Boot and Spring", ["Spring", "Spring Boot"])).toEqual([
      "Spring Boot",
      "Spring",
    ]);
    expect(marked("C++, C# and Node.js (C)", ["C++", "C#", "Node.js"])).toEqual([
      "C++",
      "C#",
      "Node.js",
    ]);
  });

  it("returns the text as one plain segment without terms", () => {
    expect(highlight("plain", [])).toEqual([{ text: "plain", match: false }]);
    expect(highlight("", ["Java"])).toEqual([]);
  });
});

it("formats points with a real minus sign", () => {
  expect([formatPoints(6.24), formatPoints(-3.1), formatPoints(0)]).toEqual([
    "+6.2 pts",
    "−3.1 pts",
    "0.0 pts",
  ]);
});

it("writes role dates", () => {
  expect(roleDates({ start: "2022-06-01", end: null })).toBe("Jun 2022 – Present");
  expect(roleDates({ start: "2019-01-01", end: "2021-12-01" })).toBe("Jan 2019 – Dec 2021");
  expect(roleDates({ start: null, end: null })).toBe("Dates not given");
});

it("names relevance factors, degree levels and tiers", () => {
  expect([1, 0.5, 0].map(relevanceLabel)).toEqual(["Relevant", "Partly relevant", "Not relevant"]);
  expect([degreeName(3), degreeName(null)]).toEqual(["Bachelor's", "Not stated"]);
  expect(TIERS.contextual.label).toBe("Inferred");
});

describe("neighbours", () => {
  const rows = ["a", "b", "c"].map((id) => ({ resume_id: id }));

  it("finds the previous and next candidate", () => {
    expect(neighbours(rows, "b")).toEqual({
      previous: rows[0],
      next: rows[2],
      position: 2,
      total: 3,
    });
    expect(neighbours(rows, "a").previous).toBeNull();
    expect(neighbours(rows, "c").next).toBeNull();
  });

  it("has no neighbours for a resume outside the ranking", () => {
    expect(neighbours(rows, "z")).toEqual({ previous: null, next: null, position: null, total: 3 });
  });
});
