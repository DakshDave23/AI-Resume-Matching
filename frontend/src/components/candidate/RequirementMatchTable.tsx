import { CheckCircle2, CircleDashed, XCircle } from "lucide-react";

import type { RequirementMatch } from "@/api/candidates";
import { Badge } from "@/components/ui/badge";
import { REQUIREMENT_STATUS } from "@/lib/candidate";
import { cn } from "@/lib/utils";

const ICONS = { covered: CheckCircle2, partial: CircleDashed, not_covered: XCircle };

/** Each JD requirement, the resume sentence closest to it, the similarity and a status. */
export function RequirementMatchTable({ matches }: { matches: RequirementMatch[] }) {
  if (matches.length === 0) {
    return <p className="text-sm text-muted-foreground">The JD has no requirement sentences.</p>;
  }
  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full text-sm">
        <thead className="bg-muted/50 text-left">
          <tr>
            <th scope="col" className="px-3 py-2 font-medium">
              Requirement
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              Best evidence in the resume
            </th>
            <th scope="col" className="px-3 py-2 font-medium whitespace-nowrap">
              Similarity
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              Status
            </th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {matches.map((m) => {
            const status = REQUIREMENT_STATUS[m.status];
            const Icon = ICONS[m.status];
            return (
              <tr key={m.requirement_id} className="align-top">
                <td className="min-w-56 px-3 py-3">
                  <p>{m.text}</p>
                  {m.requirement_type === "preferred" && (
                    <Badge variant="outline" className="mt-1">
                      Preferred
                    </Badge>
                  )}
                </td>
                <td className="min-w-56 px-3 py-3 text-muted-foreground">
                  {m.evidence ? (
                    <>
                      {/* Chunks can be long: three lines here, all of it on hover. */}
                      <p className="line-clamp-3" title={m.evidence}>
                        “{m.evidence}”
                      </p>
                      {m.evidence_section && (
                        <span className="text-xs">From {m.evidence_section}</span>
                      )}
                    </>
                  ) : (
                    "Nothing close"
                  )}
                </td>
                <td className="px-3 py-3 tabular-nums">{m.similarity.toFixed(2)}</td>
                <td className={cn("px-3 py-3 font-medium whitespace-nowrap", status.tone)}>
                  <span className="inline-flex items-center gap-1">
                    <Icon className="size-4" aria-hidden />
                    {status.label}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
