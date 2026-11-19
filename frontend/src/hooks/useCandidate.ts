import { useQuery } from "@tanstack/react-query";

import { getCandidate } from "@/api/candidates";

export function useCandidate(jobId: string, resumeId: string) {
  return useQuery({
    queryKey: ["candidate", jobId, resumeId],
    queryFn: () => getCandidate(jobId, resumeId),
  });
}
