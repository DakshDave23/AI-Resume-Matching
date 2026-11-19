import { Suspense } from "react";
import { Link, Outlet } from "react-router-dom";

import { ListSkeleton } from "@/components/common/States";
import { HealthIndicator } from "@/components/layout/HealthIndicator";
import { Button } from "@/components/ui/button";

export function AppLayout() {
  return (
    <div className="min-h-screen">
      <header className="border-b">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-6 px-4">
          <Link to="/" className="font-semibold">
            AI Resume Matcher
          </Link>
          <nav className="text-sm">
            <Link to="/" className="text-muted-foreground hover:text-foreground">
              Jobs
            </Link>
          </nav>
          <div className="ml-auto flex items-center gap-4">
            <HealthIndicator />
            <Button asChild size="sm">
              <Link to="/jobs/new">New job</Link>
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-8">
        <Suspense fallback={<ListSkeleton rows={4} label="Loading page" />}>
          <Outlet />
        </Suspense>
      </main>
    </div>
  );
}
