import { CheckCircle2, Clock, Loader2, XCircle, type LucideIcon } from "lucide-react";

import { progressOf, type Batch, type BatchFile } from "@/api/batches";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const STATUS: Record<BatchFile["parse_status"], { label: string; icon: LucideIcon; tone: string }> =
  {
    queued: { label: "Queued", icon: Clock, tone: "text-muted-foreground" },
    parsing: { label: "Parsing", icon: Loader2, tone: "text-foreground" },
    parsed: { label: "Parsed", icon: CheckCircle2, tone: "text-green-700" },
    failed: { label: "Failed", icon: XCircle, tone: "text-destructive" },
  };

/** Each file's parse status under an "N of M parsed" bar; status in words and icon, not colour alone. */
export function BatchStatusList({ batch }: { batch: Batch }) {
  const progress = progressOf(batch);
  return (
    <section aria-label="Upload progress" className="space-y-4">
      <div className="space-y-2">
        <p role="status" aria-live="polite" className="text-sm font-medium">
          {progress.label}
        </p>
        <div
          role="progressbar"
          aria-label="Files processed"
          aria-valuemin={0}
          aria-valuemax={progress.total}
          aria-valuenow={progress.done}
          className="h-2 overflow-hidden rounded-full bg-muted"
        >
          <div
            className="h-full bg-primary transition-[width] duration-500"
            style={{ width: `${progress.percent}%` }}
          />
        </div>
      </div>
      <ul className="divide-y rounded-lg border">
        {batch.files.map((file) => {
          const status = STATUS[file.parse_status];
          const Icon = status.icon;
          return (
            <li key={file.resume_id} className="flex items-start gap-3 px-4 py-3 text-sm">
              <Icon
                aria-hidden
                className={cn(
                  "mt-0.5 size-4 shrink-0",
                  status.tone,
                  file.parse_status === "parsing" && "animate-spin",
                )}
              />
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{file.filename}</p>
                {file.candidate_name && (
                  <p className="text-muted-foreground">{file.candidate_name}</p>
                )}
                {file.parse_error && <p className="text-destructive">{file.parse_error}</p>}
              </div>
              {file.needs_review && <Badge variant="outline">Check by hand</Badge>}
              <span className={cn("shrink-0 font-medium", status.tone)}>{status.label}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
