import { AlertCircle, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/errors";

/** Something couldn't load: say what, and offer to try again (not for a 404: it won't appear). */
export function ErrorState({
  error,
  fallback,
  onRetry,
}: {
  error: unknown;
  fallback: string;
  onRetry?: () => void;
}) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center gap-3 rounded-lg border border-destructive/40 p-8 text-center"
    >
      <AlertCircle className="size-6 text-destructive" aria-hidden />
      <p>{errorMessage(error, fallback)}</p>
      {onRetry && !(error instanceof ApiError && error.status === 404) && (
        <Button variant="outline" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

/** Nothing here yet: say so, and give the next thing to do. */
export function EmptyState({
  icon: Icon,
  title,
  children,
  action,
}: {
  icon: LucideIcon;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed p-10 text-center">
      <Icon className="size-8 text-muted-foreground" aria-hidden />
      <h2 className="font-medium">{title}</h2>
      {children && <div className="max-w-md text-sm text-muted-foreground">{children}</div>}
      {action && <div className="flex flex-wrap justify-center gap-2">{action}</div>}
    </div>
  );
}

/** Skeleton rows in the shape of a table or list. */
export function ListSkeleton({ rows = 5, label }: { rows?: number; label: string }) {
  return (
    <div role="status" aria-label={label} className="divide-y rounded-lg border">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-4 p-4">
          <Skeleton className="h-4 w-6" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="h-3 w-1/4" />
          </div>
          <Skeleton className="h-4 w-24" />
          <Skeleton className="hidden h-4 w-40 sm:block" />
        </div>
      ))}
    </div>
  );
}
