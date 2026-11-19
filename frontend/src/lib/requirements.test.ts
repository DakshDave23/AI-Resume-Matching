import { describe, expect, it } from "vitest";

import type { Job } from "@/api/jobs";
import {
  addChip,
  draftFromJob,
  isDirty,
  moveChip,
  removeChip,
  toUpdate,
  validate,
} from "@/lib/requirements";

function skill(id: number, name: string, type: "required" | "preferred", minYears?: number) {
  return {
    skill_id: id,
    name,
    category: "language",
    is_custom: false,
    requirement_type: type,
    weight: type === "required" ? 1 : 0.5,
    min_years: minYears ?? null,
    source_text: null,
    added_by: "parser" as const,
  };
}

const JOB = {
  id: "job-1",
  title: "Senior Backend Java Developer",
  skills: [skill(1, "Java", "required", 5), skill(2, "Kafka", "preferred")],
  unmapped_skills: ["Frobnicator"],
  min_experience_years: 4,
  max_experience_years: null,
  required_degree_level: 3,
  required_fields_of_study: ["Computer Science", "Information Technology"],
  accepts_equivalent_experience: false,
} as unknown as Job;

describe("the draft", () => {
  it("starts from the saved job and is not dirty", () => {
    const draft = draftFromJob(JOB);
    expect(draft.chips.map((c) => [c.name, c.requirementType, c.minYears])).toEqual([
      ["Java", "required", 5],
      ["Kafka", "preferred", null],
    ]);
    expect([draft.minYears, draft.maxYears, draft.fields]).toEqual([
      "4",
      "",
      "Computer Science, Information Technology",
    ]);
    expect(isDirty(draft, JOB)).toBe(false);
  });

  it("moves a chip between columns, and back", () => {
    const moved = moveChip(draftFromJob(JOB), "id:2");
    expect(moved.chips[1]?.requirementType).toBe("required");
    expect(isDirty(moved, JOB)).toBe(true);
    expect(isDirty(moveChip(moved, "id:2"), JOB)).toBe(false); // back where it was
  });

  it("removes a chip", () => {
    expect(removeChip(draftFromJob(JOB), "id:1").chips.map((c) => c.name)).toEqual(["Kafka"]);
  });

  it("adds a taxonomy skill, or a new custom one by name", () => {
    let draft = addChip(draftFromJob(JOB), { skillId: 7, name: "Docker" }, "preferred");
    draft = addChip(draft, { skillId: null, name: "  Frobnicator " }, "required");
    expect(draft.chips.slice(2)).toEqual([
      expect.objectContaining({ skillId: 7, name: "Docker", requirementType: "preferred" }),
      expect.objectContaining({ skillId: null, name: "Frobnicator", isCustom: true }),
    ]);
  });

  it("never lists a skill twice: adding it again moves it", () => {
    const draft = addChip(draftFromJob(JOB), { skillId: 2, name: "Kafka" }, "required");
    expect(draft.chips).toHaveLength(2);
    expect(draft.chips[1]?.requirementType).toBe("required");
    const byName = addChip(draftFromJob(JOB), { skillId: null, name: "java" }, "preferred");
    expect(byName.chips).toHaveLength(2);
  });

  it("ignores a blank name", () => {
    const draft = draftFromJob(JOB);
    expect(addChip(draft, { skillId: null, name: "   " }, "required")).toBe(draft);
  });
});

describe("the PATCH body", () => {
  it("sends every chip, by id or by name, and every field", () => {
    let draft = addChip(draftFromJob(JOB), { skillId: null, name: "Frobnicator" }, "preferred");
    draft = { ...draft, minYears: "3.5", maxYears: "", fields: "CS, , Statistics, CS" };
    expect(toUpdate(draft)).toEqual({
      skills: [
        { skill_id: 1, requirement_type: "required", min_years: 5 },
        { skill_id: 2, requirement_type: "preferred", min_years: null },
        { name: "Frobnicator", requirement_type: "preferred", min_years: null },
      ],
      min_experience_years: 3.5,
      max_experience_years: null,
      required_degree_level: 3,
      required_fields_of_study: ["CS", "Statistics"],
      accepts_equivalent_experience: false,
    });
  });
});

describe("validation", () => {
  it.each([
    [{ minYears: "abc" }, "Minimum years must be a number from 0 to 50."],
    [{ maxYears: "-1" }, "Maximum years must be a number from 0 to 50."],
    [{ minYears: "60" }, "Minimum years must be a number from 0 to 50."],
    [{ minYears: "5", maxYears: "3" }, "Maximum years can't be below the minimum."],
  ])("rejects %j", (changes, message) => {
    expect(validate({ ...draftFromJob(JOB), ...changes })).toBe(message);
  });

  it("accepts empty years (no minimum or maximum)", () => {
    expect(validate({ ...draftFromJob(JOB), minYears: "", maxYears: "" })).toBeNull();
  });
});
