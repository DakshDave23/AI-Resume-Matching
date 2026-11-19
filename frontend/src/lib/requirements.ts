/**
 * The requirement editor's draft and its rules, kept free of React so they're easy to test.
 *
 * The recruiter edits a local draft; "Save" sends it as one PATCH. `skills` there replaces
 * the job's whole list, so the draft always holds every chip.
 */
import type { Job, RequirementsUpdate, SkillChipIn } from "@/api/jobs";

export type RequirementType = "required" | "preferred";

export interface Chip {
  key: string; // stable within the draft: the skill id, or the name of a skill being added
  skillId: number | null; // null: a new custom skill, created on save
  name: string;
  requirementType: RequirementType;
  minYears: number | null;
  isCustom: boolean;
}

export interface Draft {
  chips: Chip[];
  minYears: string; // as typed; "" means no minimum
  maxYears: string;
  degreeLevel: number | null;
  fields: string; // comma-separated, as typed
  equivalentExperience: boolean;
}

export const DEGREE_LEVELS: { value: number; label: string }[] = [
  { value: 1, label: "High school" },
  { value: 2, label: "Diploma" },
  { value: 3, label: "Bachelor's" },
  { value: 4, label: "Master's" },
  { value: 5, label: "Doctorate" },
];

const nameKey = (name: string) => `name:${name.trim().toLowerCase()}`;

export function draftFromJob(job: Job): Draft {
  return {
    chips: job.skills.map((s) => ({
      key: `id:${s.skill_id}`,
      skillId: s.skill_id,
      name: s.name,
      requirementType: s.requirement_type,
      minYears: s.min_years ?? null,
      isCustom: s.is_custom,
    })),
    minYears: job.min_experience_years == null ? "" : String(job.min_experience_years),
    maxYears: job.max_experience_years == null ? "" : String(job.max_experience_years),
    degreeLevel: job.required_degree_level ?? null,
    fields: job.required_fields_of_study.join(", "),
    equivalentExperience: job.accepts_equivalent_experience,
  };
}

export function moveChip(draft: Draft, key: string): Draft {
  return {
    ...draft,
    chips: draft.chips.map((c) =>
      c.key === key
        ? { ...c, requirementType: c.requirementType === "required" ? "preferred" : "required" }
        : c,
    ),
  };
}

export function removeChip(draft: Draft, key: string): Draft {
  return { ...draft, chips: draft.chips.filter((c) => c.key !== key) };
}

/** Add a skill chip; a skill already on the list is moved to `type` instead of duplicated. */
export function addChip(
  draft: Draft,
  skill: { skillId: number | null; name: string; isCustom?: boolean },
  type: RequirementType,
): Draft {
  const name = skill.name.trim();
  if (!name) return draft;
  const existing = draft.chips.find(
    (c) =>
      (skill.skillId !== null && c.skillId === skill.skillId) ||
      c.name.toLowerCase() === name.toLowerCase(),
  );
  if (existing) {
    return {
      ...draft,
      chips: draft.chips.map((c) => (c === existing ? { ...c, requirementType: type } : c)),
    };
  }
  const chip: Chip = {
    key: skill.skillId !== null ? `id:${skill.skillId}` : nameKey(name),
    skillId: skill.skillId,
    name,
    requirementType: type,
    minYears: null,
    isCustom: skill.isCustom ?? skill.skillId === null,
  };
  return { ...draft, chips: [...draft.chips, chip] };
}

function years(text: string): number | null {
  const value = Number.parseFloat(text);
  return text.trim() === "" || Number.isNaN(value) ? null : value;
}

/** What's wrong with the draft, in words; null when it can be saved. */
export function validate(draft: Draft): string | null {
  for (const [label, text] of [
    ["Minimum years", draft.minYears],
    ["Maximum years", draft.maxYears],
  ] as const) {
    const value = years(text);
    if (text.trim() !== "" && (value === null || value < 0 || value > 50)) {
      return `${label} must be a number from 0 to 50.`;
    }
  }
  const low = years(draft.minYears);
  const high = years(draft.maxYears);
  if (low !== null && high !== null && high < low) {
    return "Maximum years can't be below the minimum.";
  }
  return null;
}

/** The PATCH body: every field, with `skills` as the full chip list. */
export function toUpdate(draft: Draft): RequirementsUpdate {
  const skills: SkillChipIn[] = draft.chips.map((c) =>
    c.skillId !== null
      ? { skill_id: c.skillId, requirement_type: c.requirementType, min_years: c.minYears }
      : { name: c.name, requirement_type: c.requirementType, min_years: c.minYears },
  );
  const fields = [
    ...new Set(
      draft.fields
        .split(",")
        .map((f) => f.trim())
        .filter(Boolean),
    ),
  ];
  return {
    skills,
    min_experience_years: years(draft.minYears),
    max_experience_years: years(draft.maxYears),
    required_degree_level: draft.degreeLevel as RequirementsUpdate["required_degree_level"],
    required_fields_of_study: fields,
    accepts_equivalent_experience: draft.equivalentExperience,
  };
}

/** Whether the draft differs from what's saved, compared as the request it would send. */
export function isDirty(draft: Draft, job: Job): boolean {
  return JSON.stringify(toUpdate(draft)) !== JSON.stringify(toUpdate(draftFromJob(job)));
}
