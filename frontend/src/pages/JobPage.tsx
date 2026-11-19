import { useParams } from "react-router-dom";

import { ErrorState } from "@/components/common/States";
import { RequirementsEditor } from "@/components/job/RequirementsEditor";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useJob, useUpdateRequirements } from "@/hooks/useJobs";

/** Wizard step 1, review: what the parser extracted from the JD, editable before scoring. */
export function JobPage() {
  const { jobId = "" } = useParams();
  const { data: job, error, isPending, refetch } = useJob(jobId);
  const save = useUpdateRequirements(jobId);

  if (isPending) {
    return (
      <div role="status" aria-label="Loading job" className="space-y-6">
        <Skeleton className="h-4 w-48" />
        <Skeleton className="h-8 w-2/3" />
        <div className="grid gap-4 md:grid-cols-2">
          <Skeleton className="h-40" />
          <Skeleton className="h-40" />
        </div>
      </div>
    );
  }
  if (error) {
    return (
      <ErrorState error={error} fallback="The job couldn't be loaded." onRetry={() => refetch()} />
    );
  }
  return (
    <div className="space-y-8">
      <header>
        <p className="text-sm text-muted-foreground">Step 1 of 3 · Review the requirements</p>
        <h1 className="mt-1 flex flex-wrap items-center gap-3 text-2xl font-semibold">
          {job.title}
          {job.seniority && <Badge variant="secondary">{job.seniority}</Badge>}
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {[job.company, job.location, job.source_filename].filter(Boolean).join(" · ") ||
            "Pasted job description"}
        </p>
      </header>
      {/* Keyed on the save time: after a save the editor starts again from the saved job. */}
      <RequirementsEditor key={job.updated_at} job={job} save={save} />
    </div>
  );
}
