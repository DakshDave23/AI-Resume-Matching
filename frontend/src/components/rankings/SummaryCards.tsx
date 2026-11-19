import { formatPercent, type Summary } from "@/lib/rankings";

/** Resumes ranked, average match, top match, and how many have every required skill. */
export function SummaryCards({ summary }: { summary: Summary }) {
  const cards = [
    { label: "Resumes ranked", value: String(summary.ranked) },
    {
      label: "Average match",
      value: summary.average === null ? "–" : formatPercent(summary.average),
    },
    {
      label: "Top match",
      value: summary.top ? formatPercent(summary.top.score) : "–",
      note: summary.top?.name,
    },
    {
      label: "Have every required skill",
      value: String(summary.meetsAllRequired),
      note: summary.ranked ? `of ${summary.ranked}` : undefined,
    },
  ];
  return (
    <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {cards.map((card) => (
        <div key={card.label} className="rounded-lg border p-4">
          <dt className="text-sm text-muted-foreground">{card.label}</dt>
          <dd className="mt-1 text-2xl font-semibold tabular-nums">{card.value}</dd>
          {card.note && <dd className="truncate text-sm text-muted-foreground">{card.note}</dd>}
        </div>
      ))}
    </dl>
  );
}
