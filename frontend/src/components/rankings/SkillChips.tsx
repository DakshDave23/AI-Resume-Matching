import type { RankingRow } from "@/api/rankings";
import { Badge } from "@/components/ui/badge";
import { skillChips } from "@/lib/rankings";

/** The first 4 matched skills, full-credit matches first, then "+N". */
export function SkillChips({ row }: { row: RankingRow }) {
  const { names, more } = skillChips(row);
  if (names.length === 0) return <span className="text-muted-foreground">None</span>;
  return (
    <div className="flex min-w-52 flex-wrap gap-1">
      {names.map((name) => (
        <Badge key={name} variant="secondary">
          {name}
        </Badge>
      ))}
      {more > 0 && (
        <Badge variant="outline" title={`${more} more matched skill${more === 1 ? "" : "s"}`}>
          +{more}
        </Badge>
      )}
    </div>
  );
}
