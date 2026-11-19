import { useParams } from "react-router-dom";

import { ApiError } from "@/api/client";
import { RequirementsEditor } from "@/components/job/RequirementsEditor";
import { Badge } from "@/components/ui/badge";
import { useJob, useUpdateRequirements } from "@/hooks/useJobs";

/** Wizard step 1, review: what the parser extracted from the JD, editable before scoring. */
export function JobPage() {
  const { jobId = "" } = useParams();
  const { data: job, error, isPending } = useJob(jobId);
  const save = useUpdateRequirements(jobId);

  if (isPending) {
    return <div className="h-48 animate-pulse rounded-lg bg-muted" aria-label="Loading job" />;
  }
  if (error || !job) {
    const message = error instanceof ApiError ? error.message : "The job couldn't be loaded.";
    return <p className="text-destructive">{message}</p>;
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
