import { ExternalLink } from "lucide-react";
import { useMemo } from "react";

import { highlight } from "@/lib/candidate";

/** The text extracted from the resume, with the matched skills highlighted. */
export function ResumeTextViewer({
  text,
  terms,
  fileUrl,
  filename,
}: {
  text: string | null;
  terms: string[];
  fileUrl: string;
  filename: string;
}) {
  const segments = useMemo(() => highlight(text ?? "", terms), [text, terms]);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <p className="text-muted-foreground">
          Extracted text. Matched skills are{" "}
          <mark className="rounded bg-yellow-200 px-0.5">highlighted</mark>.
        </p>
        <a
          href={fileUrl}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 font-medium hover:underline"
        >
          Open the original ({filename})
          <ExternalLink className="size-3.5" aria-hidden />
        </a>
      </div>
      {segments.length === 0 ? (
        <p className="text-sm text-muted-foreground">No text was extracted.</p>
      ) : (
        <pre className="max-h-[32rem] overflow-auto rounded-lg border bg-muted/30 p-4 font-sans text-sm whitespace-pre-wrap">
          {segments.map((s, i) =>
            s.match ? (
              <mark key={i} className="rounded bg-yellow-200 px-0.5">
                {s.text}
              </mark>
            ) : (
              s.text
            ),
          )}
        </pre>
      )}
    </div>
  );
}
