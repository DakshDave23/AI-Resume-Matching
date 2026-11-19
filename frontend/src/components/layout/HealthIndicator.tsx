import { cn } from "@/lib/utils";
import { useHealth } from "@/hooks/useHealth";
import type { Health } from "@/api/health";

type Tone = "ok" | "wait" | "down";

function describe(health: Health | undefined, failed: boolean): { tone: Tone; label: string } {
  if (failed) return { tone: "down", label: "API unreachable" };
  if (!health) return { tone: "wait", label: "Checking API…" };
  if (health.status === "ok") return { tone: "ok", label: "API ready" };
  const checks = health.checks ?? {};
  if (checks.database !== "ok") return { tone: "down", label: "Database unavailable" };
  if (checks.embedding_model === "loading") return { tone: "wait", label: "Model loading…" };
  return { tone: "down", label: "API not ready" };
}

const DOT: Record<Tone, string> = {
  ok: "bg-green-600",
  wait: "bg-amber-500 animate-pulse",
  down: "bg-red-600",
};

/** The API's state in words as well as colour (design doc §9: colour is never the only signal). */
export function HealthIndicator() {
  const { data, isError } = useHealth();
  const { tone, label } = describe(data, isError);
  return (
    <span role="status" aria-live="polite" className="flex items-center gap-2 text-sm">
      <span aria-hidden className={cn("size-2 rounded-full", DOT[tone])} />
      <span className={tone === "ok" ? "text-muted-foreground" : "font-medium"}>{label}</span>
    </span>
  );
}
