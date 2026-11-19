import { useMutation, useQuery } from "@tanstack/react-query";

import { getBatch, uploadResumes } from "@/api/batches";

export const POLL_MS = 2_000; // design doc §2: the frontend polls batch status every 2 seconds

export function useUploadResumes(jobId: string) {
  return useMutation({ mutationFn: (files: File[]) => uploadResumes(jobId, files) });
}

/** The batch's progress, polled every 2 s while it is processing, then left alone. */
export function useBatch(batchId: string | null) {
  return useQuery({
    queryKey: ["batch", batchId],
    queryFn: () => getBatch(batchId as string),
    enabled: batchId !== null,
    refetchInterval: (query) =>
      query.state.data && query.state.data.status !== "processing" ? false : POLL_MS,
  });
}
