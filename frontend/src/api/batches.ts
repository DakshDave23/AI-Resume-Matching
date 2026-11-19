import { request, type Schemas } from "@/api/client";

export type BatchCreated = Schemas["BatchCreatedOut"];
export type Batch = Schemas["BatchStatusOut"];
export type BatchFile = Schemas["BatchFileOut"];

/** 202 at once; the files are parsed in the background. */
export function uploadResumes(jobId: string, files: File[]): Promise<BatchCreated> {
  const form = new FormData();
  for (const file of files) form.append("files", file);
  return request<BatchCreated>(`/jobs/${encodeURIComponent(jobId)}/resumes`, {
    method: "POST",
    body: form,
  });
}

export function getBatch(batchId: string): Promise<Batch> {
  return request<Batch>(`/batches/${encodeURIComponent(batchId)}`);
}

export interface Progress {
  done: number; // parsed or failed
  total: number;
  parsed: number;
  failed: number;
  percent: number;
  finished: boolean;
  label: string;
}

/** "9 of 12 parsed" and the numbers behind the progress bar. */
export function progressOf(batch: Batch): Progress {
  const { processed_files: parsed, failed_files: failed, total_files: total } = batch;
  const done = parsed + failed;
  const finished = batch.status !== "processing";
  const label = finished
    ? `${parsed} of ${total} parsed${failed ? `, ${failed} failed` : ""}`
    : `${done} of ${total} processed`;
  return {
    done,
    total,
    parsed,
    failed,
    percent: total ? Math.round((100 * done) / total) : 0,
    finished,
    label,
  };
}
