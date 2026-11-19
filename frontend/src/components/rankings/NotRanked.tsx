import { Loader2, XCircle } from "lucide-react";

import type { Rankings } from "@/api/rankings";

/** The job's resumes missing from the ranking: failed ones with their reason, and any still parsing. */
export function NotRanked({ resumes }: { resumes: Rankings["not_ranked"] }) {
  const failed = resumes.filter((r) => r.parse_status === "failed");
  const pending = resumes.length - failed.length;
  if (resumes.length === 0) return null;
  return (
    <section aria-label="Resumes not ranked" className="space-y-2 rounded-lg border p-4 text-sm">
      {pending > 0 && (
        <p role="status" className="flex items-center gap-2">
          <Loader2 className="size-4 animate-spin text-muted-foreground" aria-hidden />
          {pending === 1 ? "1 resume is" : `${pending} resumes are`} still being parsed. They join
          the ranking when they're done.
        </p>
      )}
      {failed.length > 0 && (
        <>
          <h2 className="font-medium">
            {failed.length === 1 ? "1 resume couldn't" : `${failed.length} resumes couldn't`} be
            read, so {failed.length === 1 ? "it isn't" : "they aren't"} ranked
          </h2>
          <ul className="space-y-1">
            {failed.map((r) => (
              <li key={r.resume_id} className="flex items-start gap-2">
                <XCircle className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden />
                <span>
                  <span className="font-medium">{r.filename}</span>:{" "}
                  <span className="text-destructive">{r.parse_error ?? "Unknown error."}</span>
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
