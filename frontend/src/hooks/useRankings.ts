import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getRankings,
  rankingParams,
  rescore,
  saveWeights,
  type RankingFilters,
} from "@/api/rankings";
import { jobKey } from "@/hooks/useJobs";
import type { Weights } from "@/lib/weights";

const rankingsKey = (jobId: string) => ["rankings", jobId] as const;

/** The job's ranked rows. While new filters load, the previous rows stay on screen. */
export function useRankings(jobId: string, filters: RankingFilters = {}) {
  return useQuery({
    queryKey: [...rankingsKey(jobId), rankingParams(filters).toString()], // empty filters share a key
    queryFn: () => getRankings(jobId, filters),
    placeholderData: keepPreviousData,
  });
}

/** After a re-score every stored number changes: rankings, candidate pages, the job's weights. */
function useRefreshScores(jobId: string) {
  const client = useQueryClient();
  return () =>
    Promise.all([
      client.invalidateQueries({ queryKey: rankingsKey(jobId) }),
      client.invalidateQueries({ queryKey: ["candidate", jobId] }),
      client.invalidateQueries({ queryKey: jobKey(jobId) }),
    ]);
}

/** POST /match: re-score with the job's current requirements and weights. */
export function useRescore(jobId: string) {
  const refresh = useRefreshScores(jobId);
  return useMutation({ mutationFn: () => rescore(jobId), onSuccess: refresh });
}

/** PATCH /weights (fractions): saves them and re-scores every candidate. */
export function useSaveWeights(jobId: string) {
  const refresh = useRefreshScores(jobId);
  return useMutation({
    mutationFn: (weights: Weights) => saveWeights(jobId, weights),
    onSuccess: refresh,
  });
}
