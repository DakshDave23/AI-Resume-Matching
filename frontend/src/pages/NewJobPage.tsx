import { useNavigate } from "react-router-dom";

import { ApiError } from "@/api/client";
import { JdInput } from "@/components/job/JdInput";
import { useCreateJob } from "@/hooks/useJobs";

/** Wizard step 1: paste or upload the JD; the parser's extraction opens for review. */
export function NewJobPage() {
  const navigate = useNavigate();
  const create = useCreateJob();

  return (
    <div className="max-w-3xl space-y-6">
      <header>
        <p className="text-sm text-muted-foreground">Step 1 of 3 · Job description</p>
        <h1 className="mt-1 text-2xl font-semibold">New job</h1>
        <p className="mt-2 text-muted-foreground">
          Paste or upload a job description. Its skills, years and degree are extracted for you to
          review.
        </p>
      </header>
      <JdInput
        pending={create.isPending}
        onSubmit={(input) =>
          create.mutate(input, { onSuccess: (job) => navigate(`/jobs/${job.id}`) })
        }
      />
      {create.isError && (
        <p role="alert" className="text-sm text-destructive">
          {create.error instanceof ApiError
            ? create.error.message
            : "The job description couldn't be read."}
        </p>
      )}
    </div>
  );
}
