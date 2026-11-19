import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getRankings, rescore, type RankingFilters } from "@/api/rankings";

const rankingsKey = (jobId: string) => ["rankings", jobId] as const;

/** The job's ranked rows. While new filters load, the previous rows stay on screen. */
export function useRankings(jobId: string, filters: RankingFilters = {}) {
  return useQuery({
    queryKey: [...rankingsKey(jobId), filters],
    queryFn: () => getRankings(jobId, filters),
    placeholderData: keepPreviousData,
  });
}

/** POST /match, then reload every view of this job's ranking. */
export function useRescore(jobId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => rescore(jobId),
    onSuccess: () => client.invalidateQueries({ queryKey: rankingsKey(jobId) }),
  });
}
