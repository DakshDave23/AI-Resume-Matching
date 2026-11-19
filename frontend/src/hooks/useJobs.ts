import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createJob,
  getJob,
  listJobs,
  loadSampleData,
  searchSkills,
  updateRequirements,
  uploadJob,
  type Job,
  type RequirementsUpdate,
} from "@/api/jobs";

export const jobKey = (jobId: string) => ["job", jobId] as const;

export function useJob(jobId: string) {
  return useQuery({ queryKey: jobKey(jobId), queryFn: () => getJob(jobId) });
}

/** Paste or upload a JD; the new job goes straight into the cache. */
export function useCreateJob() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: { title?: string; text: string } | File) =>
      input instanceof File ? uploadJob(input) : createJob(input),
    onSuccess: (job: Job) => client.setQueryData(jobKey(job.id), job),
  });
}

export function useUpdateRequirements(jobId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: RequirementsUpdate) => updateRequirements(jobId, body),
    onSuccess: (job: Job) => client.setQueryData(jobKey(jobId), job),
  });
}

export function useSkillSearch(query: string) {
  const q = query.trim();
  return useQuery({
    queryKey: ["skills", q.toLowerCase()],
    queryFn: () => searchSkills(q),
    enabled: q.length > 0,
    staleTime: 60_000,
  });
}

export function useJobList() {
  // Counts and top scores change with every upload: always refetch when the page opens.
  return useQuery({ queryKey: ["jobs"], queryFn: () => listJobs(), staleTime: 0 });
}

export function useLoadSampleData() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: loadSampleData,
    onSuccess: () => client.invalidateQueries({ queryKey: ["jobs"] }),
  });
}
