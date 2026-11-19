import type { Candidate } from "@/api/candidates";
import { relevanceLabel, roleDates } from "@/lib/candidate";
import { formatYears } from "@/lib/rankings";
import { cn } from "@/lib/utils";

const FACTOR_TONE = (factor: number) =>
  factor >= 1 ? "text-green-700" : factor > 0 ? "text-amber-700" : "text-muted-foreground";

/** Required years against total and relevant years, then each role and how much of it counts. */
export function ExperienceComparison({ candidate }: { candidate: Candidate }) {
  const experience = candidate.explanation.details.experience;
  const required =
    experience.min_years === null
      ? "None stated"
      : experience.max_years === null
        ? `${experience.min_years}+ yrs`
        : `${experience.min_years}–${experience.max_years} yrs`;
  const stats = [
    { label: "Required", value: required },
    { label: "Total", value: formatYears(candidate.total_years) },
    { label: "Relevant", value: formatYears(candidate.relevant_years) },
  ];
  return (
    <div className="space-y-6">
      <dl className="grid grid-cols-3 gap-3">
        {stats.map((s) => (
          <div key={s.label} className="rounded-lg border p-3">
            <dt className="text-sm text-muted-foreground">{s.label}</dt>
            <dd className="mt-1 text-lg font-semibold">{s.value}</dd>
          </div>
        ))}
      </dl>
      {experience.above_max && (
        <p className="text-sm text-amber-700">More experience than the role's stated maximum.</p>
      )}
      <section aria-label="Roles" className="space-y-2">
        <h3 className="font-medium">Roles</h3>
        <p className="text-sm text-muted-foreground">
          Each month counts once, at the most relevant role held that month, so overlapping jobs are
          not counted twice.
        </p>
        {experience.roles.length === 0 ? (
          <p className="text-sm text-muted-foreground">No roles with dates were found.</p>
        ) : (
          <ul className="divide-y rounded-lg border">
            {experience.roles.map((role, i) => (
              <li key={i} className="flex flex-wrap items-start gap-x-4 gap-y-1 p-3 text-sm">
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{role.title ?? "Untitled role"}</p>
                  <p className="text-muted-foreground">
                    {[role.company, roleDates(role)].filter(Boolean).join(" · ")}
                    {role.months !== null && ` · ${formatYears(role.months / 12)}`}
                  </p>
                </div>
                <div className="text-right">
                  <p className={cn("font-medium", FACTOR_TONE(role.factor))}>
                    {relevanceLabel(role.factor)} (×{role.factor})
                  </p>
                  {role.similarity !== null && (
                    <p className="text-xs text-muted-foreground">
                      Similarity to the JD {role.similarity.toFixed(2)}
                    </p>
                  )}
                  {!role.counted && (
                    <p className="text-xs text-muted-foreground">
                      Not counted (internship or no dates)
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
