import { Briefcase, Database, Plus } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

import type { JobSummary } from "@/api/jobs";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/common/States";
import { Button } from "@/components/ui/button";
import { useJobList, useLoadSampleData } from "@/hooks/useJobs";
import { formatPercent } from "@/lib/rankings";

const DATE = new Intl.DateTimeFormat(undefined, { dateStyle: "medium" });

/** Where a job opens: its ranking once it has resumes, else the next wizard step. */
function jobPath(job: JobSummary): string {
  return job.resume_count > 0 ? `/jobs/${job.id}/rankings` : `/jobs/${job.id}`;
}

/** Jobs home: every job with its date, resume count and best match; or the way to start. */
export function JobsPage() {
  const navigate = useNavigate();
  const { data, error, isPending, refetch } = useJobList();
  const sample = useLoadSampleData();

  function loadSample() {
    // Straight to the upload page, where the 15 samples parse live (one fails, with its reason).
    sample.mutate(undefined, {
      onSuccess: (batch) => navigate(`/jobs/${batch.job_id}/upload?batch=${batch.batch_id}`),
    });
  }

  const actions = (
    <>
      <Button asChild>
        <Link to="/jobs/new">
          <Plus aria-hidden /> New job
        </Link>
      </Button>
      <Button variant="outline" onClick={loadSample} disabled={sample.isPending}>
        <Database aria-hidden /> {sample.isPending ? "Loading sample data…" : "Load sample data"}
      </Button>
    </>
  );

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Jobs</h1>
          <p className="mt-1 text-muted-foreground">
            Your job descriptions and their ranked candidates.
          </p>
        </div>
        {data && data.items.length > 0 && <div className="flex gap-2">{actions}</div>}
      </header>

      {error ? (
        <ErrorState
          error={error}
          fallback="The jobs couldn't be loaded."
          onRetry={() => refetch()}
        />
      ) : isPending ? (
        <ListSkeleton rows={4} label="Loading jobs" />
      ) : data.items.length === 0 ? (
        <EmptyState icon={Briefcase} title="No jobs yet" action={actions}>
          Start with a job description, or load the sample Backend Java job with 15 synthetic
          resumes to see the whole flow.
        </EmptyState>
      ) : (
        <section aria-label="Jobs" className="space-y-2">
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-left">
                <tr>
                  <th scope="col" className="px-4 py-2 font-medium">
                    Job
                  </th>
                  <th scope="col" className="px-4 py-2 font-medium">
                    Created
                  </th>
                  <th scope="col" className="px-4 py-2 text-right font-medium">
                    Resumes
                  </th>
                  <th scope="col" className="px-4 py-2 text-right font-medium">
                    Top match
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {data.items.map((job) => (
                  <tr key={job.id} className="hover:bg-muted/30">
                    <td className="px-4 py-3">
                      <Link to={jobPath(job)} className="font-medium hover:underline">
                        {job.title}
                      </Link>
                      {job.company && <p className="text-muted-foreground">{job.company}</p>}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-muted-foreground">
                      {DATE.format(new Date(job.created_at))}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">{job.resume_count}</td>
                    <td className="px-4 py-3 text-right tabular-nums">
                      {job.top_score === null ? "–" : formatPercent(job.top_score)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.total > data.items.length && (
            <p className="text-sm text-muted-foreground">
              Showing the newest {data.items.length} of {data.total} jobs.
            </p>
          )}
        </section>
      )}
    </div>
  );
}
