"use client";

// Audit Log table (TanStack Table v8, fully server-driven). Pagination and both
// filter kinds are `manual*` — the table renders state but never paginates or
// filters in the browser. The single source of truth is `pagination` +
// `columnFilters` React state; that state is mapped to an `AuditQuery` and fetched
// via `useAuditLog`. Any filter change resets to page 0 so a narrowed result set
// can't strand the user on a now-empty page. Text filters are debounced.

import { useEffect, useMemo, useState } from "react";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type Column,
  type ColumnDef,
  type ColumnFiltersState,
  type OnChangeFn,
  type PaginationState,
} from "@tanstack/react-table";
import { type DateRange } from "react-day-picker";
import { useAuditLog, type AuditEntry, type AuditQuery } from "@/lib/api/audit";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/app/Components/ui/popover";
import { Calendar } from "@/app/Components/ui/calendar";

// Which columns are filterable and how. Multi-select option sets mirror the
// engine's enums (orbital_engine/security/attributes.py + the decision CHECK).
type FilterConfig =
  | { kind: "text" }
  | { kind: "multiselect"; options: string[] }
  | { kind: "daterange" };
const FILTERS: Record<string, FilterConfig> = {
  ts: { kind: "daterange" },
  subject: { kind: "text" },
  path: { kind: "text" },
  source_ip: { kind: "text" },
  decision: { kind: "multiselect", options: ["permit", "deny"] },
  role: { kind: "multiselect", options: ["VIEWER", "ANALYST", "ADMIN"] },
  domain: {
    kind: "multiselect",
    options: [
      "CATALOG",
      "SCREENING",
      "MANEUVER_INTEL",
      "REPORTS",
      "AUDIT",
      "ADMIN",
    ],
  },
  action: {
    kind: "multiselect",
    options: ["READ", "QUERY", "EXPORT", "ACKNOWLEDGE", "ADMINISTER"],
  },
};

const dash = (v: string | null) => v ?? "—";

const COLUMNS: ColumnDef<AuditEntry>[] = [
  {
    accessorKey: "ts",
    header: "Time",
    cell: ({ getValue }) => new Date(getValue<string>()).toLocaleString(),
  },
  {
    accessorKey: "subject",
    header: "Subject",
    cell: ({ getValue }) => dash(getValue<string | null>()),
  },
  {
    accessorKey: "role",
    header: "Role",
    cell: ({ getValue }) => dash(getValue<string | null>()),
  },
  { accessorKey: "domain", header: "Domain" },
  { accessorKey: "action", header: "Action" },
  {
    accessorKey: "decision",
    header: "Decision",
    cell: ({ getValue }) => {
      const d = getValue<string>();
      return (
        <span
          className={`font-medium ${
            d === "deny" ? "text-red-400" : "text-emerald-400"
          }`}
        >
          {d}
        </span>
      );
    },
  },
  { accessorKey: "reason", header: "Reason" },
  {
    accessorKey: "source_ip",
    header: "Source IP",
    cell: ({ getValue }) => dash(getValue<string | null>()),
  },
  {
    accessorKey: "path",
    header: "Path",
    cell: ({ getValue }) => dash(getValue<string | null>()),
  },
];

/** Debounce a changing value — used to throttle server hits from text typing. */
function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(id);
  }, [value, delayMs]);
  return debounced;
}

/** Free-text "contains" filter; commits to column state only after debounce. */
function TextFilter({ column }: { column: Column<AuditEntry, unknown> }) {
  const [value, setValue] = useState((column.getFilterValue() as string) ?? "");
  const debounced = useDebouncedValue(value, 350);
  useEffect(() => {
    column.setFilterValue(debounced.trim() ? debounced.trim() : undefined);
  }, [debounced, column]);
  return (
    <input
      value={value}
      onChange={(e) => setValue(e.target.value)}
      placeholder="Search…"
      className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-1.5 py-0.5 text-xs font-normal text-slate-200 placeholder:text-slate-600 focus:border-slate-500 focus:outline-none"
    />
  );
}

/** Multi-select dropdown; selected values are applied as an inclusive-OR filter. */
function MultiSelectFilter({
  column,
  options,
}: {
  column: Column<AuditEntry, unknown>;
  options: string[];
}) {
  const selected = (column.getFilterValue() as string[] | undefined) ?? [];
  const toggle = (opt: string) => {
    const next = selected.includes(opt)
      ? selected.filter((s) => s !== opt)
      : [...selected, opt];
    column.setFilterValue(next.length ? next : undefined);
  };
  return (
    <details className="group relative mt-1 font-normal">
      <summary className="flex cursor-pointer list-none items-center justify-between rounded border border-slate-700 bg-slate-950 px-1.5 py-0.5 text-xs text-slate-200 marker:hidden">
        <span>{selected.length ? `${selected.length} selected` : "All"}</span>
        <span className="text-slate-500 group-open:rotate-180">▾</span>
      </summary>
      <div className="absolute z-10 mt-1 max-h-56 w-40 overflow-auto rounded border border-slate-700 bg-slate-900 p-1 shadow-lg">
        {options.map((opt) => (
          <label
            key={opt}
            className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-xs text-slate-200 hover:bg-slate-800"
          >
            <input
              type="checkbox"
              checked={selected.includes(opt)}
              onChange={() => toggle(opt)}
              className="accent-emerald-500"
            />
            {opt}
          </label>
        ))}
      </div>
    </details>
  );
}

// Day boundaries so a picked range filters whole days inclusively.
const startOfDay = (d: Date) => {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  return x;
};
const endOfDay = (d: Date) => {
  const x = new Date(d);
  x.setHours(23, 59, 59, 999);
  return x;
};

/** Filter value stored for the timestamp column: ISO bounds (either may be set). */
type TsRange = { from?: string; to?: string };

/** shadcn date-range picker; selecting a range filters `ts` server-side. */
function DateRangeFilter({ column }: { column: Column<AuditEntry, unknown> }) {
  const value = column.getFilterValue() as TsRange | undefined;
  const selected: DateRange | undefined =
    value?.from || value?.to
      ? {
          from: value?.from ? new Date(value.from) : undefined,
          to: value?.to ? new Date(value.to) : undefined,
        }
      : undefined;

  const label =
    selected?.from || selected?.to
      ? `${selected?.from ? selected.from.toLocaleDateString() : "…"} – ${
          selected?.to ? selected.to.toLocaleDateString() : "…"
        }`
      : "All dates";

  const onSelect = (range: DateRange | undefined) => {
    const from = range?.from ? startOfDay(range.from).toISOString() : undefined;
    const to = range?.to ? endOfDay(range.to).toISOString() : undefined;
    column.setFilterValue(from || to ? { from, to } : undefined);
  };

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button className="mt-1 flex w-full items-center justify-between rounded border border-slate-700 bg-slate-950 px-1.5 py-0.5 text-left text-xs font-normal text-slate-200">
          <span className="truncate">{label}</span>
          <span className="ml-1 text-slate-500">▾</span>
        </button>
      </PopoverTrigger>
      <PopoverContent>
        <Calendar
          mode="range"
          selected={selected}
          onSelect={onSelect}
          numberOfMonths={2}
          defaultMonth={selected?.from}
        />
        {(selected?.from || selected?.to) && (
          <button
            onClick={() => column.setFilterValue(undefined)}
            className="mt-2 w-full rounded border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800"
          >
            Clear
          </button>
        )}
      </PopoverContent>
    </Popover>
  );
}

export default function AuditTable() {
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 25,
  });
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);
  // Bumped on "Clear filters" to remount the debounced text inputs (their local
  // state isn't otherwise notified of an external reset).
  const [filtersNonce, setFiltersNonce] = useState(0);

  // Any filter change must reset to the first page (a narrowed set can't strand
  // the user on a page that no longer exists).
  const handleColumnFiltersChange: OnChangeFn<ColumnFiltersState> = (
    updater
  ) => {
    setColumnFilters(updater);
    setPagination((p) => (p.pageIndex === 0 ? p : { ...p, pageIndex: 0 }));
  };

  const clearFilters = () => {
    setColumnFilters([]);
    setPagination((p) => (p.pageIndex === 0 ? p : { ...p, pageIndex: 0 }));
    setFiltersNonce((n) => n + 1);
  };

  // Map controlled state -> the typed server query.
  const query = useMemo<AuditQuery>(() => {
    const q: AuditQuery = {
      pageIndex: pagination.pageIndex,
      pageSize: pagination.pageSize,
    };
    for (const f of columnFilters) {
      switch (f.id) {
        case "subject":
          q.subject = f.value as string;
          break;
        case "path":
          q.path = f.value as string;
          break;
        case "source_ip":
          q.source_ip = f.value as string;
          break;
        case "ts": {
          const r = f.value as TsRange;
          q.tsFrom = r.from;
          q.tsTo = r.to;
          break;
        }
        case "decision":
          q.decision = f.value as string[];
          break;
        case "role":
          q.role = f.value as string[];
          break;
        case "domain":
          q.domain = f.value as string[];
          break;
        case "action":
          q.action = f.value as string[];
          break;
      }
    }
    return q;
  }, [columnFilters, pagination]);

  const { data, isLoading, isFetching, isError } = useAuditLog(query);
  const rows = data?.rows ?? [];
  const total = data?.total ?? 0;

  const table = useReactTable({
    data: rows,
    columns: COLUMNS,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualFiltering: true,
    rowCount: total,
    state: { pagination, columnFilters },
    onPaginationChange: setPagination,
    onColumnFiltersChange: handleColumnFiltersChange,
  });

  const { pageIndex, pageSize } = table.getState().pagination;
  const pageCount = table.getPageCount();

  return (
    <main className="min-h-screen bg-black px-8 pt-20 pb-8 text-slate-200">
      <div className="flex items-center gap-3 mb-4">
        <h1 className="text-2xl font-semibold">Audit Log</h1>
        {isFetching && (
          <span className="text-xs text-slate-500">Updating…</span>
        )}
        {columnFilters.length > 0 && (
          <button
            onClick={clearFilters}
            className="ml-auto rounded border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800"
          >
            Clear filters
          </button>
        )}
      </div>

      {isError ? (
        <p className="text-sm text-red-400">Failed to load the audit log.</p>
      ) : (
        <>
          <div className="max-h-[calc(100vh-20rem)] overflow-auto rounded-lg border border-slate-800">
            <table className="w-full text-left text-xs">
              <thead className="sticky top-0 z-20 bg-slate-900 text-slate-400 align-top">
                {table.getHeaderGroups().map((hg) => (
                  <tr key={hg.id}>
                    {hg.headers.map((header) => {
                      const filter = FILTERS[header.column.id];
                      return (
                        <th
                          key={header.id}
                          className="bg-slate-900 px-3 py-2 font-medium"
                        >
                          {flexRender(
                            header.column.columnDef.header,
                            header.getContext()
                          )}
                          {filter?.kind === "text" && (
                            <TextFilter
                              key={filtersNonce}
                              column={header.column}
                            />
                          )}
                          {filter?.kind === "multiselect" && (
                            <MultiSelectFilter
                              column={header.column}
                              options={filter.options}
                            />
                          )}
                          {filter?.kind === "daterange" && (
                            <DateRangeFilter column={header.column} />
                          )}
                        </th>
                      );
                    })}
                  </tr>
                ))}
              </thead>
              <tbody>
                {isLoading ? (
                  <tr>
                    <td
                      colSpan={COLUMNS.length}
                      className="px-3 py-6 text-center text-slate-500"
                    >
                      Loading audit log…
                    </td>
                  </tr>
                ) : table.getRowModel().rows.length === 0 ? (
                  <tr>
                    <td
                      colSpan={COLUMNS.length}
                      className="h-64 px-3 py-6 text-center align-middle text-slate-500"
                    >
                      No matching audit entries.
                    </td>
                  </tr>
                ) : (
                  table.getRowModel().rows.map((row) => (
                    <tr key={row.id} className="border-t border-slate-800/60">
                      {row.getVisibleCells().map((cell) => (
                        <td
                          key={cell.id}
                          className="px-3 py-1.5 whitespace-nowrap"
                        >
                          {flexRender(
                            cell.column.columnDef.cell,
                            cell.getContext()
                          )}
                        </td>
                      ))}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination controls (all navigation triggers a server request). */}
          <div className="flex flex-wrap items-center mt-2 gap-2 text-xs text-slate-400">
            <button
              onClick={() => table.firstPage()}
              disabled={!table.getCanPreviousPage()}
              className="rounded border border-slate-700 px-2 py-1 disabled:opacity-40"
            >
              « First
            </button>
            <button
              onClick={() => table.previousPage()}
              disabled={!table.getCanPreviousPage()}
              className="rounded border border-slate-700 px-2 py-1 disabled:opacity-40"
            >
              ‹ Prev
            </button>
            <button
              onClick={() => table.nextPage()}
              disabled={!table.getCanNextPage()}
              className="rounded border border-slate-700 px-2 py-1 disabled:opacity-40"
            >
              Next ›
            </button>
            <button
              onClick={() => table.lastPage()}
              disabled={!table.getCanNextPage()}
              className="rounded border border-slate-700 px-2 py-1 disabled:opacity-40"
            >
              Last »
            </button>

            <span className="ml-2">
              Page {pageCount === 0 ? 0 : pageIndex + 1} of {pageCount}
            </span>

            <span className="ml-2 flex items-center gap-1">
              Jump to
              <input
                type="number"
                min={1}
                max={Math.max(pageCount, 1)}
                value={pageIndex + 1}
                onChange={(e) => {
                  const n = Number(e.target.value) - 1;
                  if (Number.isFinite(n)) {
                    table.setPageIndex(
                      Math.min(Math.max(n, 0), Math.max(pageCount - 1, 0))
                    );
                  }
                }}
                className="w-14 rounded border border-slate-700 bg-slate-950 px-1.5 py-0.5 text-slate-200 focus:border-slate-500 focus:outline-none"
              />
            </span>

            <select
              value={pageSize}
              onChange={(e) => table.setPageSize(Number(e.target.value))}
              className="ml-2 rounded border border-slate-700 bg-slate-950 px-1.5 py-1 text-slate-200 focus:border-slate-500 focus:outline-none"
            >
              {[10, 25, 50, 100].map((n) => (
                <option key={n} value={n}>
                  {n} / page
                </option>
              ))}
            </select>

            <span className="ml-auto text-slate-500">{total} total</span>
          </div>
        </>
      )}
    </main>
  );
}
