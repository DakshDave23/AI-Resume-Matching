import { request, type Schemas } from "@/api/client";

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
