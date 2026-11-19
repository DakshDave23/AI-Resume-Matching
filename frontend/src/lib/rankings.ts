import type { RankingRow } from "@/api/rankings";

export interface Summary {
  ranked: number;
  average: number | null; // mean match %, 1 decimal
  top: { score: number; name: string } | null;
  meetsAllRequired: number; // no required skill missing
}

/** The dashboard's summary cards, from the unfiltered ranking. */
export function summarize(rows: RankingRow[]): Summary {
  if (rows.length === 0) return { ranked: 0, average: null, top: null, meetsAllRequired: 0 };
  const best = rows.reduce((a, b) => (b.match_percent > a.match_percent ? b : a));
  const mean = rows.reduce((sum, r) => sum + r.match_percent, 0) / rows.length;
  return {
    ranked: rows.length,
    average: Math.round(mean * 10) / 10,
    top: { score: best.match_percent, name: displayName(best) },
    meetsAllRequired: rows.filter((r) => r.missing_required_count === 0).length,
  };
}

/** The candidate's name, or the file name when the parser found none. */
export function displayName(row: Pick<RankingRow, "name" | "filename">): string {
  return row.name ?? row.filename;
}

export function formatPercent(value: number): string {
  return `${value.toFixed(1)}%`;
}

export function formatYears(years: number | null): string {
  if (years === null) return "Unknown";
  return `${years.toFixed(1)} ${years === 1 ? "yr" : "yrs"}`;
}

/** The verdict word for a match (from the API), so colour is never the only signal. */
export const VERDICTS: Record<string, { label: string; bar: string; text: string }> = {
  strong: { label: "Strong", bar: "bg-green-600", text: "text-green-700" },
  good: { label: "Good", bar: "bg-sky-600", text: "text-sky-700" },
  partial: { label: "Partial", bar: "bg-amber-500", text: "text-amber-700" },
  weak: { label: "Weak", bar: "bg-zinc-400", text: "text-muted-foreground" },
};

export function verdictOf(verdict: string | null) {
  return (verdict && VERDICTS[verdict]) || { label: "Unscored", bar: "bg-zinc-300", text: "" };
}

/** The first `shown` matched skills, and how many more there are. */
export function skillChips(row: RankingRow, shown = 4): { names: string[]; more: number } {
  const names = row.top_matched_skills.slice(0, shown);
  return { names, more: Math.max(0, row.matched_skill_count - names.length) };
}
