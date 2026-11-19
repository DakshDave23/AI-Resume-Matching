import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ApiError } from "@/api/client";
import type { RankingFilters } from "@/api/rankings";
import { RankingTable } from "@/components/rankings/RankingTable";
import { SummaryCards } from "@/components/rankings/SummaryCards";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { useJob } from "@/hooks/useJobs";
import { useRankings, useRescore } from "@/hooks/useRankings";
import { summarize } from "@/lib/rankings";

const MIN_SCORES = [0, 50, 65, 80];
const SELECT =
  "h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm shadow-xs focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none";

function errorText(error: unknown): string {
  return error instanceof ApiError ? error.message : "The ranking couldn't be loaded.";
}

/** Wizard step 3: summary cards over the ranked table, with search and filters. */
export function RankingsPage() {
  const { jobId = "" } = useParams();
  const { data: job } = useJob(jobId);

  const [search, setSearch] = useState("");
  const [minScore, setMinScore] = useState(0);
  const [skill, setSkill] = useState("");
  const filters: RankingFilters = { search: useDebouncedValue(search), minScore, skill };
  const filtered = search.trim() !== "" || minScore > 0 || skill !== "";

  const everyone = useRankings(jobId); // the cards always describe the whole ranking
  const shown = useRankings(jobId, filters);
  const rescore = useRescore(jobId);

  const all = everyone.data?.rows ?? [];
  const rows = shown.data?.rows ?? [];
  const stale = all.some((r) => r.is_stale);

  function clearFilters() {
    setSearch("");
    setMinScore(0);
    setSkill("");
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm text-muted-foreground">Step 3 of 3 · Rankings</p>
          <h1 className="mt-1 text-2xl font-semibold">{job?.title ?? "Rankings"}</h1>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" asChild>
            <Link to={`/jobs/${jobId}`}>Requirements</Link>
          </Button>
          <Button variant="outline" asChild>
            <Link to={`/jobs/${jobId}/upload`}>Upload resumes</Link>
          </Button>
        </div>
      </header>

      {everyone.error ? (
        <p role="alert" className="text-sm text-destructive">
          {errorText(everyone.error)}
        </p>
      ) : everyone.isPending ? (
        <div className="h-24 animate-pulse rounded-lg bg-muted" aria-label="Loading summary" />
      ) : (
        <SummaryCards summary={summarize(all)} />
      )}

      {stale && (
        <div
          role="status"
          className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm"
        >
          <p>The requirements changed after these scores were worked out.</p>
          <Button size="sm" onClick={() => rescore.mutate()} disabled={rescore.isPending}>
            {rescore.isPending ? "Re-scoring…" : "Re-score now"}
          </Button>
          {rescore.isError && (
            <p role="alert" className="w-full text-destructive">
              {errorText(rescore.error)}
            </p>
          )}
        </div>
      )}

      <section
        aria-label="Filters"
        className="grid gap-3 sm:grid-cols-[2fr_1fr_1fr_auto] sm:items-end"
      >
        <div className="space-y-1.5">
          <Label htmlFor="search">Search</Label>
          <Input
            id="search"
            type="search"
            placeholder="Name, title or file name"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="min-score">Minimum match</Label>
          <select
            id="min-score"
            className={SELECT}
            value={minScore}
            onChange={(e) => setMinScore(Number(e.target.value))}
          >
            {MIN_SCORES.map((n) => (
              <option key={n} value={n}>
                {n === 0 ? "Any match" : `${n}% or more`}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="skill">Has skill</Label>
          <select
            id="skill"
            className={SELECT}
            value={skill}
            onChange={(e) => setSkill(e.target.value)}
          >
            <option value="">Any skill</option>
            {(["required", "preferred"] as const).map((type) => (
              <optgroup key={type} label={type === "required" ? "Required" : "Preferred"}>
                {job?.skills
                  .filter((s) => s.requirement_type === type)
                  .map((s) => (
                    <option key={s.skill_id} value={s.name}>
                      {s.name}
                    </option>
                  ))}
              </optgroup>
            ))}
          </select>
        </div>
        <Button variant="ghost" onClick={clearFilters} disabled={!filtered}>
          Clear filters
        </Button>
      </section>

      {shown.error ? (
        <p role="alert" className="text-sm text-destructive">
          {errorText(shown.error)}
        </p>
      ) : shown.isPending ? (
        <div className="h-64 animate-pulse rounded-lg bg-muted" aria-label="Loading ranking" />
      ) : all.length === 0 ? (
        <p className="rounded-lg border p-8 text-center text-muted-foreground">
          No resumes are ranked for this job yet.{" "}
          <Link to={`/jobs/${jobId}/upload`} className="font-medium text-foreground underline">
            Upload resumes
          </Link>
        </p>
      ) : rows.length === 0 ? (
        <p className="rounded-lg border p-8 text-center text-muted-foreground">
          No candidates match these filters.
        </p>
      ) : (
        <section aria-label="Ranked candidates" className="space-y-2">
          <p className="text-sm text-muted-foreground" aria-live="polite">
            {filtered
              ? `Showing ${rows.length} of ${all.length} candidates`
              : `${all.length} candidates`}
          </p>
          <RankingTable jobId={jobId} rows={rows} />
        </section>
      )}
    </div>
  );
}
