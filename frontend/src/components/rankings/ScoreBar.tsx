import { formatPercent, verdictOf } from "@/lib/rankings";
import { cn } from "@/lib/utils";

/** Match % as a number, a bar and the verdict word. */
export function ScoreBar({ score, verdict }: { score: number; verdict: string | null }) {
  const v = verdictOf(verdict);
  return (
    <div className="w-36 space-y-1">
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-semibold tabular-nums">{formatPercent(score)}</span>
        <span className={cn("text-xs font-medium", v.text)}>{v.label}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-muted" aria-hidden>
        <div className={cn("h-full", v.bar)} style={{ width: `${Math.min(100, score)}%` }} />
      </div>
    </div>
  );
}
