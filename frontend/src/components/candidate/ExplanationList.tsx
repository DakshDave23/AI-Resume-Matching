import { CheckCircle2, MinusCircle } from "lucide-react";

import type { EvidenceItem } from "@/api/candidates";
import { formatPoints } from "@/lib/candidate";
import { cn } from "@/lib/utils";

/** Strengths (points earned) or gaps (points lost), each with its points and resume evidence. */
export function ExplanationList({
  title,
  items,
  kind,
  empty,
}: {
  title: string;
  items: EvidenceItem[];
  kind: "strength" | "gap";
  empty: string;
}) {
  const Icon = kind === "strength" ? CheckCircle2 : MinusCircle;
  const tone = kind === "strength" ? "text-green-700" : "text-destructive";
  return (
    <section aria-label={title} className="space-y-2">
      <h3 className="font-medium">{title}</h3>
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">{empty}</p>
      ) : (
        <ul className="space-y-3">
          {items.map((item, i) => (
            <li key={`${item.type}-${i}`} className="flex gap-2 text-sm">
              <Icon className={cn("mt-0.5 size-4 shrink-0", tone)} aria-hidden />
              <div className="min-w-0 flex-1">
                <p>
                  {item.message}{" "}
                  <span className={cn("font-medium whitespace-nowrap tabular-nums", tone)}>
                    {formatPoints(item.impact)}
                  </span>
                </p>
                {item.snippet && (
                  <blockquote className="mt-1 border-l-2 pl-2 text-muted-foreground">
                    “{item.snippet}”
                    {item.section && <span className="ml-1 text-xs">({item.section})</span>}
                  </blockquote>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
