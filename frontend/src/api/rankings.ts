import { API_BASE_URL, request, type Schemas } from "@/api/client";

export type Rankings = Schemas["RankingsOut"];
export type RankingRow = Schemas["RankingRow"];
export type MatchRun = Schemas["MatchRunOut"];

/** The toolbar's filters; empty values are left out of the request. */
export interface RankingFilters {
  search?: string;
  minScore?: number;
  skill?: string;
}

export function rankingParams(filters: RankingFilters): URLSearchParams {
  const params = new URLSearchParams();
  const search = filters.search?.trim();
  if (search) params.set("search", search);
  if (filters.minScore !== undefined && filters.minScore > 0) {
    params.set("min_score", String(filters.minScore));
  }
  if (filters.skill) params.set("skill", filters.skill);
  return params;
}

export function getRankings(jobId: string, filters: RankingFilters = {}): Promise<Rankings> {
  const query = rankingParams(filters).toString();
  return request<Rankings>(
    `/jobs/${encodeURIComponent(jobId)}/rankings${query ? `?${query}` : ""}`,
  );
}

/** Re-score every parsed resume with the job's current requirements and weights. */
export function rescore(jobId: string): Promise<MatchRun> {
  return request<MatchRun>(`/jobs/${encodeURIComponent(jobId)}/match`, { method: "POST" });
}

export type WeightsSaved = Schemas["WeightsOut"];

/** Save the four weights; the API re-scores every candidate with them. */
export function saveWeights(
  jobId: string,
  weights: Record<"skills" | "semantic" | "experience" | "education", number>,
): Promise<WeightsSaved> {
  return request<WeightsSaved>(`/jobs/${encodeURIComponent(jobId)}/weights`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(weights),
  });
}

/** The CSV download for the saved ranking, with the same filters as the table. */
export function exportUrl(jobId: string, filters: RankingFilters = {}): string {
  const query = rankingParams(filters).toString();
  return `${API_BASE_URL}/jobs/${encodeURIComponent(jobId)}/rankings/export${query ? `?${query}` : ""}`;
}
