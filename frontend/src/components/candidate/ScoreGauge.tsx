import { formatPercent, verdictOf } from "@/lib/rankings";
import { cn } from "@/lib/utils";

const RADIUS = 52;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

/** The match % as a ring, with the verdict word under the number. */
export function ScoreGauge({ score, verdict }: { score: number; verdict: string | null }) {
  const v = verdictOf(verdict);
  const filled = (Math.min(100, Math.max(0, score)) / 100) * CIRCUMFERENCE;
  return (
    <div
      className="relative size-36 shrink-0"
      role="img"
      aria-label={`Match ${formatPercent(score)}, ${v.label.toLowerCase()} match`}
    >
      <svg viewBox="0 0 120 120" className="size-full -rotate-90" aria-hidden>
        <circle cx="60" cy="60" r={RADIUS} fill="none" strokeWidth="10" className="stroke-muted" />
        <circle
          cx="60"
          cy="60"
          r={RADIUS}
          fill="none"
          strokeWidth="10"
          strokeLinecap="round"
          stroke="currentColor"
          strokeDasharray={`${filled} ${CIRCUMFERENCE}`}
          className={v.text}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center" aria-hidden>
        <span className="text-2xl font-semibold tabular-nums">{formatPercent(score)}</span>
        <span className={cn("text-sm font-medium", v.text)}>{v.label} match</span>
      </div>
    </div>
  );
}
