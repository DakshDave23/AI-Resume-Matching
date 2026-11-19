import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from "@tanstack/react-table";
import { AlertTriangle, ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import type { RankingRow } from "@/api/rankings";
import { ScoreBar } from "@/components/rankings/ScoreBar";
import { SkillChips } from "@/components/rankings/SkillChips";
import { displayName, formatYears } from "@/lib/rankings";

const column = createColumnHelper<RankingRow>();

/** The table's columns; links to the candidate page need the job id. */
function columnsFor(jobId: string) {
  return [
    column.accessor((r) => r.rank ?? undefined, {
      id: "rank",
      header: "Rank",
      sortUndefined: "last",
      cell: (c) => <span className="tabular-nums">{c.getValue() ?? "–"}</span>,
    }),
    column.accessor((r) => displayName(r).toLowerCase(), {
      id: "candidate",
      header: "Candidate",
      sortingFn: "text",
      cell: ({ row: { original: r } }) => (
        <div className="min-w-40">
          <Link
            to={`/jobs/${jobId}/candidates/${r.resume_id}`}
            className="font-medium hover:underline"
          >
            {displayName(r)}
          </Link>
          <p className="text-muted-foreground">{r.current_title ?? "No current title"}</p>
        </div>
      ),
    }),
    column.accessor((r) => r.relevant_years ?? undefined, {
      id: "experience",
      header: "Experience",
      sortUndefined: "last",
      sortDescFirst: true,
      cell: ({ row: { original: r } }) => (
        <div className="whitespace-nowrap">
          <p>{formatYears(r.total_years)} total</p>
          <p className="text-muted-foreground">{formatYears(r.relevant_years)} relevant</p>
        </div>
      ),
    }),
    column.accessor("match_percent", {
      id: "match",
      header: "Match",
      sortDescFirst: true,
      cell: ({ row: { original: r } }) => <ScoreBar score={r.match_percent} verdict={r.verdict} />,
    }),
    column.display({
      id: "skills",
      header: "Matched skills",
      cell: ({ row: { original: r } }) => <SkillChips row={r} />,
    }),
    column.accessor("missing_required_count", {
      id: "missing",
      header: "Missing required",
      cell: (c) => (
        <span className="tabular-nums">{c.getValue() === 0 ? "None" : c.getValue()}</span>
      ),
    }),
    column.accessor((r) => r.parse_confidence ?? undefined, {
      id: "parse",
      header: "Parse quality",
      sortUndefined: "last",
      cell: ({ row: { original: r } }) =>
        r.needs_review ? (
          <span className="inline-flex items-center gap-1 whitespace-nowrap text-amber-700">
            <AlertTriangle className="size-4" aria-hidden />
            Check by hand
          </span>
        ) : (
          <span className="tabular-nums">
            {r.parse_confidence === null ? "–" : `${Math.round(r.parse_confidence * 100)}%`}
          </span>
        ),
    }),
  ];
}

/**
 * The ranked candidates, in the API's order until a column header is clicked.
 * Sorting is done here on the rows the API returned, so it never changes who is shown.
 */
export function RankingTable({ jobId, rows }: { jobId: string; rows: RankingRow[] }) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const columns = useMemo(() => columnsFor(jobId), [jobId]);
  // React Compiler can't memoise TanStack Table v8; this app doesn't use the compiler.
  // eslint-disable-next-line react-hooks/incompatible-library
  const table = useReactTable({
    data: rows,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getRowId: (r) => r.resume_id,
  });

  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full text-sm">
        <thead className="bg-muted/50 text-left">
          {table.getHeaderGroups().map((group) => (
            <tr key={group.id}>
              {group.headers.map((header) => {
                const sorted = header.column.getIsSorted();
                const Icon =
                  sorted === "asc" ? ArrowUp : sorted === "desc" ? ArrowDown : ArrowUpDown;
                const label = flexRender(header.column.columnDef.header, header.getContext());
                return (
                  <th
                    key={header.id}
                    scope="col"
                    className="px-3 py-2 font-medium whitespace-nowrap"
                    aria-sort={
                      sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : undefined
                    }
                  >
                    {header.column.getCanSort() ? (
                      <button
                        type="button"
                        onClick={header.column.getToggleSortingHandler()}
                        className="inline-flex items-center gap-1 hover:text-foreground"
                      >
                        {label}
                        <Icon
                          className={sorted ? "size-3.5" : "size-3.5 text-muted-foreground"}
                          aria-hidden
                        />
                      </button>
                    ) : (
                      label
                    )}
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody className="divide-y">
          {table.getRowModel().rows.map((row) => (
            <tr key={row.id} className="align-top hover:bg-muted/30">
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id} className="px-3 py-3">
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
