import type { MatchedSkill, RequirementMatch, Role } from "@/api/candidates";

/** Tier badges, as the design doc names them (§7): "contextual" reads as "Inferred". */
export const TIERS: Record<MatchedSkill["tier"], { label: string; hint: string }> = {
  exact: { label: "Exact", hint: "Named on the resume" },
  alias: { label: "Alias", hint: "Named under another spelling" },
  related: { label: "Related", hint: "A closely related skill, at partial credit" },
  contextual: { label: "Inferred", hint: "Not named, but described in the experience" },
};

export const REQUIREMENT_STATUS: Record<
  RequirementMatch["status"],
  { label: string; tone: string }
> = {
  covered: { label: "Covered", tone: "text-green-700" },
  partial: { label: "Partial", tone: "text-amber-700" },
  not_covered: { label: "Not covered", tone: "text-destructive" },
};

const DEGREES = ["No degree", "High school", "Diploma", "Bachelor's", "Master's", "Doctorate"];

export function degreeName(level: number | null): string {
  return level === null ? "Not stated" : (DEGREES[level] ?? "Unknown");
}

const MINUS = "−";

/** "+6.2 pts" for points earned, "−3.1 pts" for points lost. */
export function formatPoints(points: number): string {
  const sign = points > 0 ? "+" : points < 0 ? MINUS : "";
  return `${sign}${Math.abs(points).toFixed(1)} pts`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function monthYear(iso: string): string {
  const [year, month] = iso.split("-");
  return `${MONTHS[Number(month) - 1] ?? ""} ${year}`.trim();
}

/** "Jun 2022 – Present". */
export function roleDates(role: Pick<Role, "start" | "end">): string {
  if (!role.start) return "Dates not given";
  return `${monthYear(role.start)} – ${role.end ? monthYear(role.end) : "Present"}`;
}

/** How a role's relevance factor counts towards relevant experience. */
export function relevanceLabel(factor: number): string {
  if (factor >= 1) return "Relevant";
  if (factor > 0) return "Partly relevant";
  return "Not relevant";
}

/** Previous and next candidate in the ranking, from the rows in rank order. */
export function neighbours<T extends { resume_id: string }>(rows: T[], resumeId: string) {
  const index = rows.findIndex((r) => r.resume_id === resumeId);
  if (index < 0) return { previous: null, next: null, position: null, total: rows.length };
  return {
    previous: rows[index - 1] ?? null,
    next: rows[index + 1] ?? null,
    position: index + 1,
    total: rows.length,
  };
}

export interface Segment {
  text: string;
  match: boolean;
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Split `text` so each whole-word, case-insensitive occurrence of a term is its own segment.
 * Longer terms win ("Spring Boot" before "Spring"); "C++" and "Node.js" work.
 */
export function highlight(text: string, terms: string[]): Segment[] {
  const unique = [...new Set(terms.map((t) => t.trim()).filter(Boolean))];
  if (unique.length === 0 || !text) return text ? [{ text, match: false }] : [];
  unique.sort((a, b) => b.length - a.length);
  const pattern = new RegExp(`(?<![\\w])(${unique.map(escapeRegExp).join("|")})(?![\\w])`, "gi");
  const segments: Segment[] = [];
  let last = 0;
  for (const found of text.matchAll(pattern)) {
    const start = found.index;
    if (start > last) segments.push({ text: text.slice(last, start), match: false });
    segments.push({ text: found[0], match: true });
    last = start + found[0].length;
  }
  if (last < text.length) segments.push({ text: text.slice(last), match: false });
  return segments;
}
