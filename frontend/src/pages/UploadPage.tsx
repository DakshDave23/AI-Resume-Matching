import { X } from "lucide-react";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { ErrorState, ListSkeleton } from "@/components/common/States";
import { BatchStatusList } from "@/components/upload/BatchStatusList";
import { FileDropzone } from "@/components/upload/FileDropzone";
import { Button } from "@/components/ui/button";
import { progressOf } from "@/api/batches";
import { useBatch, useUploadResumes } from "@/hooks/useBatches";
import { useJob } from "@/hooks/useJobs";
import { checkFiles, formatSize, type Rejection } from "@/lib/files";

/**
 * Wizard step 2: choose resumes, upload them, watch each one parse.
 * The batch id lives in the URL (?batch=…), so a reload keeps showing its progress.
 */
export function UploadPage() {
  const { jobId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const batchId = params.get("batch");
  const { data: job } = useJob(jobId);
  const upload = useUploadResumes(jobId);
  const { data: batch, error: batchError, refetch } = useBatch(batchId);

  const [chosen, setChosen] = useState<File[]>([]);
  const [rejected, setRejected] = useState<Rejection[]>([]);

  function addFiles(files: File[]) {
    const checked = checkFiles(files, chosen);
    setChosen((current) => [...current, ...checked.accepted]);
    setRejected(checked.rejected);
  }

  function startUpload() {
    upload.mutate(chosen, {
      onSuccess: (created) => {
        // Files the API refused (e.g. not really a PDF) are reported with the API's reason.
        setRejected(created.rejected.map((r) => ({ name: r.filename, reason: r.message })));
        setChosen([]);
        setParams({ batch: created.batch_id });
      },
    });
  }

  const progress = batch ? progressOf(batch) : null;

  return (
    <div className="max-w-3xl space-y-6">
      <header>
        <p className="text-sm text-muted-foreground">Step 2 of 3 · Upload resumes</p>
        <h1 className="mt-1 text-2xl font-semibold">{job?.title ?? "Upload resumes"}</h1>
        <p className="mt-2 text-muted-foreground">
          Each resume is read, parsed and scored against this job in the background.
        </p>
      </header>

      {rejected.length > 0 && (
        <section
          aria-label="Files not uploaded"
          className="rounded-lg border border-destructive/40 p-4 text-sm"
        >
          <h2 className="font-medium">
            {rejected.length === 1 ? "1 file wasn't" : `${rejected.length} files weren't`} added
          </h2>
          <ul className="mt-2 space-y-1">
            {rejected.map((r) => (
              <li key={`${r.name}:${r.reason}`}>
                <span className="font-medium">{r.name}</span>:{" "}
                <span className="text-destructive">{r.reason}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {batchId === null ? (
        <>
          <FileDropzone onFiles={addFiles} disabled={upload.isPending} />
          {chosen.length > 0 && (
            <section aria-label="Files to upload" className="space-y-3">
              <ul className="divide-y rounded-lg border">
                {chosen.map((file) => (
                  <li
                    key={`${file.name}:${file.size}`}
                    className="flex items-center gap-3 px-4 py-2 text-sm"
                  >
                    <span className="min-w-0 flex-1 truncate">{file.name}</span>
                    <span className="text-muted-foreground">{formatSize(file.size)}</span>
                    <button
                      type="button"
                      aria-label={`Remove ${file.name}`}
                      className="text-muted-foreground hover:text-foreground"
                      onClick={() => setChosen((current) => current.filter((f) => f !== file))}
                    >
                      <X className="size-4" aria-hidden />
                    </button>
                  </li>
                ))}
              </ul>
              <div className="flex items-center gap-3">
                <Button onClick={startUpload} disabled={upload.isPending}>
                  {upload.isPending
                    ? "Uploading…"
                    : `Upload ${chosen.length} resume${chosen.length === 1 ? "" : "s"}`}
                </Button>
                <Button variant="ghost" onClick={() => setChosen([])} disabled={upload.isPending}>
                  Clear
                </Button>
              </div>
            </section>
          )}
        </>
      ) : batchError ? (
        <ErrorState
          error={batchError}
          fallback="The upload's progress couldn't be loaded."
          onRetry={() => refetch()}
        />
      ) : batch ? (
        <>
          <BatchStatusList batch={batch} />
          <div className="flex items-center gap-3">
            {progress?.finished ? (
              <Button asChild>
                <Link to={`/jobs/${jobId}/rankings`}>Next: see the rankings</Link>
              </Button>
            ) : (
              <Button disabled>Parsing…</Button>
            )}
            <Button
              variant="ghost"
              onClick={() => {
                setRejected([]);
                setParams({});
              }}
            >
              Upload more resumes
            </Button>
          </div>
        </>
      ) : (
        <ListSkeleton rows={6} label="Loading progress" />
      )}
    </div>
  );
}
