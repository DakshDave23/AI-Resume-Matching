import { X } from "lucide-react";

import { SkillAutocomplete, type PickedSkill } from "@/components/job/SkillAutocomplete";
import type { Chip, RequirementType } from "@/lib/requirements";

const COLUMNS: { type: RequirementType; title: string; other: string }[] = [
  { type: "required", title: "Required", other: "preferred" },
  { type: "preferred", title: "Preferred", other: "required" },
];

/** Skill chips in Required and Preferred columns: click to move, × to remove, + to add. */
export function RequirementChips({
  chips,
  onMove,
  onRemove,
  onAdd,
}: {
  chips: Chip[];
  onMove: (key: string) => void;
  onRemove: (key: string) => void;
  onAdd: (skill: PickedSkill, type: RequirementType) => void;
}) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {COLUMNS.map(({ type, title, other }) => {
        const column = chips.filter((c) => c.requirementType === type);
        return (
          <section key={type} aria-label={`${title} skills`} className="rounded-lg border p-4">
            <h3 className="mb-3 text-sm font-medium">
              {title} <span className="text-muted-foreground">({column.length})</span>
            </h3>
            <ul className="mb-3 flex min-h-8 flex-wrap gap-2">
              {column.length === 0 && (
                <li className="text-sm text-muted-foreground">No {title.toLowerCase()} skills.</li>
              )}
              {column.map((chip) => (
                <li
                  key={chip.key}
                  className="flex items-center rounded-full border bg-secondary text-sm"
                >
                  <button
                    type="button"
                    onClick={() => onMove(chip.key)}
                    title={`Move to ${other}`}
                    aria-label={`${chip.name}: move to ${other}`}
                    className="rounded-l-full py-1 pr-1 pl-3 hover:bg-accent"
                  >
                    {chip.name}
                    {chip.minYears !== null && (
                      <span className="ml-1 text-muted-foreground">{chip.minYears}+ yrs</span>
                    )}
                    {chip.isCustom && <span className="ml-1 text-muted-foreground">(custom)</span>}
                  </button>
                  <button
                    type="button"
                    onClick={() => onRemove(chip.key)}
                    aria-label={`Remove ${chip.name}`}
                    className="rounded-r-full py-1 pr-2 pl-1 text-muted-foreground hover:text-foreground"
                  >
                    <X className="size-3.5" aria-hidden />
                  </button>
                </li>
              ))}
            </ul>
            <SkillAutocomplete
              label={`Add a ${type} skill`}
              onPick={(skill) => onAdd(skill, type)}
            />
          </section>
        );
      })}
    </div>
  );
}
