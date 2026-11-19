import type { Breakdown } from "@/api/candidates";

/** Points earned against points available per component; the earned points add up to the match %. */
export function ScoreBreakdown({ parts, total }: { parts: Breakdown[]; total: number }) {
  return (
    <div className="min-w-0 flex-1 space-y-3">
      <h2 className="font-medium">Score breakdown</h2>
      <ul className="space-y-3">
        {parts.map((part) => (
          <li key={part.component} className="space-y-1 text-sm">
            <div className="flex justify-between gap-3">
              <span>{part.label}</span>
              <span className="tabular-nums text-muted-foreground">
                {part.active ? (
                  <>
                    <span className="font-medium text-foreground">{part.earned.toFixed(1)}</span> of{" "}
                    {part.available.toFixed(1)} pts
                  </>
                ) : (
                  "Not scored"
                )}
              </span>
            </div>
            <div
              role="meter"
              aria-label={`${part.label} points`}
              aria-valuemin={0}
              aria-valuemax={part.available}
              aria-valuenow={part.earned}
              className="h-2 overflow-hidden rounded-full bg-muted"
            >
              <div
                className="h-full bg-primary"
                style={{
                  width: part.available > 0 ? `${(part.earned / part.available) * 100}%` : "0%",
                }}
              />
            </div>
            {!part.active && (
              <p className="text-xs text-muted-foreground">
                Nothing to score it on, so its weight went to the other parts.
              </p>
            )}
          </li>
        ))}
      </ul>
      <p className="border-t pt-2 text-sm">
        Total: <span className="font-semibold tabular-nums">{total.toFixed(1)}</span> of 100 points
      </p>
    </div>
  );
}
