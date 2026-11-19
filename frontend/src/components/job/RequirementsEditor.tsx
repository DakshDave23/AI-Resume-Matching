import { useState } from "react";
import { Link } from "react-router-dom";

import type { Job } from "@/api/jobs";
import { RequirementChips } from "@/components/job/RequirementChips";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useUpdateRequirements } from "@/hooks/useJobs";
import {
  addChip,
  DEGREE_LEVELS,
  draftFromJob,
  isDirty,
  moveChip,
  removeChip,
  toUpdate,
  validate,
  type Draft,
} from "@/lib/requirements";

/**
 * The review panel: edit what the parser extracted, then save it with one PATCH.
 * `save` comes from the page, so its status outlives the editor restarting after a save.
 */
export function RequirementsEditor({
  job,
  save,
}: {
  job: Job;
  save: ReturnType<typeof useUpdateRequirements>;
}) {
  const [draft, setDraft] = useState<Draft>(() => draftFromJob(job));
  const problem = validate(draft);
  const dirty = isDirty(draft, job);
  const set = (changes: Partial<Draft>) => setDraft((d) => ({ ...d, ...changes }));
  const chipNames = new Set(draft.chips.map((c) => c.name.toLowerCase()));
  const unmapped = job.unmapped_skills.filter((term) => !chipNames.has(term.toLowerCase()));

  return (
    <form
      className="space-y-6"
      onSubmit={(e) => {
        e.preventDefault();
        if (!problem && dirty) save.mutate(toUpdate(draft));
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="space-y-1.5">
          <Label htmlFor="min-years">Minimum years</Label>
          <Input
            id="min-years"
            inputMode="decimal"
            value={draft.minYears}
            onChange={(e) => set({ minYears: e.target.value })}
            placeholder="None"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="max-years">Maximum years</Label>
          <Input
            id="max-years"
            inputMode="decimal"
            value={draft.maxYears}
            onChange={(e) => set({ maxYears: e.target.value })}
            placeholder="None"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="degree">Degree</Label>
          <select
            id="degree"
            value={draft.degreeLevel ?? ""}
            onChange={(e) =>
              set({ degreeLevel: e.target.value === "" ? null : Number(e.target.value) })
            }
            className="h-9 w-full rounded-md border bg-transparent px-3 text-sm shadow-xs"
          >
            <option value="">Not required</option>
            {DEGREE_LEVELS.map((d) => (
              <option key={d.value} value={d.value}>
                {d.label}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="fields">Fields of study</Label>
          <Input
            id="fields"
            value={draft.fields}
            onChange={(e) => set({ fields: e.target.value })}
            placeholder="e.g. Computer Science, IT"
          />
        </div>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={draft.equivalentExperience}
          onChange={(e) => set({ equivalentExperience: e.target.checked })}
        />
        Accepts equivalent experience instead of the degree
      </label>

      <RequirementChips
        chips={draft.chips}
        onMove={(key) => setDraft((d) => moveChip(d, key))}
        onRemove={(key) => setDraft((d) => removeChip(d, key))}
        onAdd={(skill, type) => setDraft((d) => addChip(d, skill, type))}
      />

      {unmapped.length > 0 && (
        <section className="rounded-lg border border-dashed p-4 text-sm">
          <h3 className="font-medium">Not in the skills list</h3>
          <p className="mb-2 text-muted-foreground">
            The JD mentions these, but they aren't known skills. Add one to the taxonomy as a
            required skill:
          </p>
          <ul className="flex flex-wrap gap-2">
            {unmapped.map((term) => (
              <li key={term}>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    setDraft((d) =>
                      addChip(d, { skillId: null, name: term, isCustom: true }, "required"),
                    )
                  }
                >
                  Add “{term}” to taxonomy
                </Button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="flex flex-wrap items-center gap-3 border-t pt-4">
        <Button type="submit" disabled={!dirty || !!problem || save.isPending}>
          {save.isPending ? "Saving…" : "Save changes"}
        </Button>
        <Button
          type="button"
          variant="ghost"
          disabled={!dirty}
          onClick={() => setDraft(draftFromJob(job))}
        >
          Discard
        </Button>
        <p role="status" aria-live="polite" className="text-sm">
          {problem ? (
            <span className="text-destructive">{problem}</span>
          ) : save.isError ? (
            <span className="text-destructive">Not saved.</span>
          ) : dirty ? (
            <span className="text-muted-foreground">Unsaved changes</span>
          ) : save.isSuccess ? (
            <span className="text-muted-foreground">All changes saved</span>
          ) : null}
        </p>
        <div className="ml-auto">
          {dirty ? (
            <Button type="button" disabled title="Save your changes first">
              Next: upload resumes
            </Button>
          ) : (
            <Button asChild>
              <Link to={`/jobs/${job.id}/upload`}>Next: upload resumes</Link>
            </Button>
          )}
        </div>
      </div>
    </form>
  );
}
