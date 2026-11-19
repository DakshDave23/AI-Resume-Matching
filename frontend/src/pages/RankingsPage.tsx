import { Download, FileSearch, SlidersHorizontal, Upload } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { exportUrl, type RankingFilters } from "@/api/rankings";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/common/States";
import { NotRanked } from "@/components/rankings/NotRanked";
import { RankingTable, type TableRow } from "@/components/rankings/RankingTable";
import { SummaryCards } from "@/components/rankings/SummaryCards";
import { WeightSliders } from "@/components/rankings/WeightSliders";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { useJob } from "@/hooks/useJobs";
import { useRankings, useRescore, useSaveWeights } from "@/hooks/useRankings";
import { summarize } from "@/lib/rankings";
import {
  DEFAULT_WEIGHTS,
  EQUIVALENT_EXPERIENCE_FACTOR,
  rerank,
  sameWeights,
  toFractions,
  toSliders,
  type Weights,
} from "@/lib/weights";

const MIN_SCORES = [0, 50, 65, 80];
const SELECT =
  "h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm shadow-xs focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none";

/**
 * Wizard step 3: summary cards over the ranked table, with search, filters and weight sliders.
 * Search and skill are filtered by the API. The minimum match is applied here, to the score
 * on screen, so it also holds while the sliders preview new weights.
 */
export function RankingsPage() {
  const { jobId = "" } = useParams();
  const { data: job } = useJob(jobId);

  const [search, setSearch] = useState("");
  const [minScore, setMinScore] = useState(0);
  const [skill, setSkill] = useState("");
  const debouncedSearch = useDebouncedValue(search);
  const filtered = search.trim() !== "" || minScore > 0 || skill !== "";

  const everyone = useRankings(jobId); // the cards always describe the whole ranking
  const shown = useRankings(jobId, { search: debouncedSearch, skill });
  const rescore = useRescore(jobId);
  const save = useSaveWeights(jobId);

  // Weights: the sliders' draft previews a new ranking until it is saved.
  const [showWeights, setShowWeights] = useState(false);
  const [draft, setDraft] = useState<Weights | null>(null);
  const saved = job ? toSliders(job.scoring_weights) : DEFAULT_WEIGHTS;
  const weights = draft ?? saved;
  const previewing = draft !== null && !sameWeights(draft, saved);
  const educationFactor = job?.accepts_equivalent_experience ? EQUIVALENT_EXPERIENCE_FACTOR : 1;

  const stored = everyone.data?.rows ?? [];
  const all: TableRow[] = previewing ? rerank(stored, weights, educationFactor) : stored;
  const shownIds = new Set((shown.data?.rows ?? []).map((r) => r.resume_id));
  const rows = (
    previewing ? all.filter((r) => shownIds.has(r.resume_id)) : (shown.data?.rows ?? [])
  ).filter((r) => r.match_percent >= minScore);
  const stale = stored.some((r) => r.is_stale);
  const exportFilters: RankingFilters = { search: debouncedSearch, minScore, skill };

  function saveWeights() {
    save.mutate(toFractions(weights), { onSuccess: () => setDraft(null) });
  }

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
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            aria-expanded={showWeights}
            aria-controls="weights-panel"
            onClick={() => setShowWeights((open) => !open)}
          >
            <SlidersHorizontal aria-hidden /> Weights
          </Button>
          <Button variant="outline" asChild>
            <a href={exportUrl(jobId, exportFilters)} download>
              <Download aria-hidden /> Export CSV
            </a>
          </Button>
          <Button variant="outline" asChild>
            <Link to={`/jobs/${jobId}`}>Requirements</Link>
          </Button>
          <Button variant="outline" asChild>
            <Link to={`/jobs/${jobId}/upload`}>Upload resumes</Link>
          </Button>
        </div>
      </header>

      {everyone.error ? (
        <ErrorState
          error={everyone.error}
          fallback="The ranking couldn't be loaded."
          onRetry={() => everyone.refetch()}
        />
      ) : everyone.isPending ? (
        <div
          role="status"
          aria-label="Loading summary"
          className="grid grid-cols-2 gap-3 lg:grid-cols-4"
        >
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      ) : (
        <>
          <SummaryCards summary={summarize(all)} />
          <NotRanked resumes={everyone.data.not_ranked} />
        </>
      )}

      {showWeights && (
        <div id="weights-panel">
          <WeightSliders
            weights={weights}
            onChange={setDraft}
            onSave={saveWeights}
            onReset={() => setDraft({ ...DEFAULT_WEIGHTS })}
            dirty={previewing}
            saving={save.isPending}
            educationHalved={educationFactor < 1}
          />
          {previewing && (
            <p className="mt-2 text-sm text-muted-foreground">
              The CSV export uses the saved weights.
            </p>
          )}
        </div>
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

      {everyone.error ? null : shown.error ? (
        <ErrorState
          error={shown.error}
          fallback="The ranking couldn't be loaded."
          onRetry={() => shown.refetch()}
        />
      ) : shown.isPending || everyone.isPending ? (
        <ListSkeleton rows={6} label="Loading ranking" />
      ) : all.length === 0 ? (
        <EmptyState
          icon={Upload}
          title="No ranked resumes yet"
          action={
            <Button asChild>
              <Link to={`/jobs/${jobId}/upload`}>Upload resumes</Link>
            </Button>
          }
        >
          Upload resumes for this job. Each one is scored as soon as it's parsed.
        </EmptyState>
      ) : rows.length === 0 ? (
        <EmptyState
          icon={FileSearch}
          title="No candidates match these filters"
          action={
            <Button variant="outline" onClick={clearFilters}>
              Clear filters
            </Button>
          }
        />
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
