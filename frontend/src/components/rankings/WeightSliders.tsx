import { Button } from "@/components/ui/button";
import { COMPONENT_LABELS, COMPONENTS, shares, type Weights } from "@/lib/weights";

/**
 * One slider per score component. The table re-ranks as they move (a preview from the stored
 * component scores); "Save" persists the weights and "Reset" goes back to the defaults.
 */
export function WeightSliders({
  weights,
  onChange,
  onSave,
  onReset,
  dirty,
  saving,
  educationHalved,
  error,
}: {
  weights: Weights;
  onChange: (weights: Weights) => void;
  onSave: () => void;
  onReset: () => void;
  dirty: boolean;
  saving: boolean;
  educationHalved: boolean;
  error: string | null;
}) {
  const share = shares(weights);
  const allZero = COMPONENTS.every((c) => weights[c] === 0);
  return (
    <section aria-label="Scoring weights" className="space-y-4 rounded-lg border p-4">
      <div className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
        {COMPONENTS.map((c) => (
          <div key={c} className="space-y-1">
            <div className="flex items-baseline justify-between text-sm">
              <label htmlFor={`weight-${c}`} className="font-medium">
                {COMPONENT_LABELS[c]}
              </label>
              <span className="text-muted-foreground tabular-nums">
                {Math.round(share[c] * 100)}% of the score
              </span>
            </div>
            <input
              id={`weight-${c}`}
              type="range"
              min={0}
              max={100}
              step={5}
              value={weights[c]}
              onChange={(e) => onChange({ ...weights, [c]: Number(e.target.value) })}
              aria-valuetext={`${weights[c]}, ${Math.round(share[c] * 100)}% of the score`}
              className="w-full accent-primary"
            />
          </div>
        ))}
      </div>
      <p className="text-xs text-muted-foreground">
        Weights are relative: only their shares matter. A part with nothing to score on (for example
        education when the JD names no degree) passes its share to the others
        {educationHalved && "; this JD accepts equivalent experience, so education counts half"}.
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={onSave} disabled={!dirty || saving || allZero}>
          {saving ? "Saving…" : "Save weights"}
        </Button>
        <Button variant="ghost" onClick={onReset} disabled={saving}>
          Reset to defaults
        </Button>
        <span className="text-sm text-muted-foreground" aria-live="polite">
          {allZero
            ? "At least one weight must be above 0."
            : dirty
              ? "Previewing: the table shows these weights. Save to keep them."
              : "These are the saved weights."}
        </span>
      </div>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
    </section>
  );
}
