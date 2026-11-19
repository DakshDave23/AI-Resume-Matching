import { CheckCircle2, XCircle } from "lucide-react";

import type { MatchedSkill, MissingSkill } from "@/api/candidates";
import { Badge } from "@/components/ui/badge";
import { TIERS } from "@/lib/candidate";

function evidenceOf(m: MatchedSkill): string {
  const via = m.matched_skill ? `Via ${m.matched_skill}. ` : "";
  return `${TIERS[m.tier].hint}. ${via}${m.evidence ? `Evidence: “${m.evidence}”` : ""}`.trim();
}

function Matched({ title, skills }: { title: string; skills: MatchedSkill[] }) {
  if (skills.length === 0) return null;
  return (
    <div className="space-y-2">
      <h4 className="text-sm text-muted-foreground">{title}</h4>
      <ul className="flex flex-wrap gap-2">
        {skills.map((m) => (
          <li
            key={m.skill}
            title={evidenceOf(m)}
            className="inline-flex items-center gap-1.5 rounded-full border py-1 pr-1 pl-2.5 text-sm"
          >
            <CheckCircle2 className="size-3.5 text-green-700" aria-hidden />
            {m.skill}
            {m.matched_skill && (
              <span className="text-xs text-muted-foreground">via {m.matched_skill}</span>
            )}
            <Badge variant={m.tier === "exact" || m.tier === "alias" ? "secondary" : "outline"}>
              {TIERS[m.tier].label}
            </Badge>
            <span className="sr-only">{evidenceOf(m)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Missing({ title, skills }: { title: string; skills: MissingSkill[] }) {
  return (
    <div className="space-y-2">
      <h4 className="text-sm text-muted-foreground">{title}</h4>
      {skills.length === 0 ? (
        <p className="text-sm">None missing.</p>
      ) : (
        <ul className="flex flex-wrap gap-2">
          {skills.map((m) => (
            <li
              key={m.skill}
              className="inline-flex items-center gap-1.5 rounded-full border border-destructive/40 px-2.5 py-1 text-sm text-destructive"
            >
              <XCircle className="size-3.5" aria-hidden />
              {m.skill}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Matched skills with their tier (evidence on hover), then missing required and preferred. */
export function SkillsPanel({
  matched,
  missing,
}: {
  matched: MatchedSkill[];
  missing: MissingSkill[];
}) {
  const byType = <T extends { requirement_type: string }>(list: T[], type: string) =>
    list.filter((s) => s.requirement_type === type);
  return (
    <div className="space-y-6">
      <section aria-label="Matched skills" className="space-y-3">
        <h3 className="font-medium">Matched skills ({matched.length})</h3>
        {matched.length === 0 && <p className="text-sm">No JD skill was found.</p>}
        <Matched title="Required" skills={byType(matched, "required")} />
        <Matched title="Preferred" skills={byType(matched, "preferred")} />
        <p className="text-xs text-muted-foreground">
          Exact and Alias get full credit. Related and Inferred get partial credit. Hover over a
          skill to see the evidence.
        </p>
      </section>
      <section aria-label="Missing skills" className="space-y-3">
        <h3 className="font-medium">Missing skills ({missing.length})</h3>
        <Missing title="Required" skills={byType(missing, "required")} />
        <Missing title="Preferred" skills={byType(missing, "preferred")} />
      </section>
    </div>
  );
}
