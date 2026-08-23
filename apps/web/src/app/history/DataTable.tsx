"use client";

// Shared client-side table for the 분석 이력 page (TanStack Table v8). Unlike
// AuditTable (server-driven `manual*`), the full dataset is already in memory —
// sorting, the single global text filter, and pagination all run in the browser.
// Styling reuses AuditTable's Tailwind vocabulary so the two read as one system.

import { useState } from "react";
import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { t } from "@/lib/i18n/t";

interface DataTableProps<TData> {
  columns: ColumnDef<TData, unknown>[];
  data: TData[] | undefined;
  isLoading: boolean;
  isError?: boolean;
  /** When set, renders a single global "contains" filter input. */
  searchPlaceholder?: string;
  emptyText?: string;
  initialSorting?: SortingState;
  pageSize?: number;
}

// Stable fallback so an undefined `data` doesn't recreate the array per render.
const EMPTY: never[] = [];

export default function DataTable<TData>({
  columns,
  data,
  isLoading,
  isError = false,
  searchPlaceholder,
  emptyText,
  initialSorting = [],
  pageSize = 25,
}: DataTableProps<TData>) {
  const [sorting, setSorting] = useState<SortingState>(initialSorting);
  const [globalFilter, setGlobalFilter] = useState("");

  const table = useReactTable({
    data: data ?? EMPTY,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    globalFilterFn: "includesString",
    state: { sorting, globalFilter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    initialState: { pagination: { pageIndex: 0, pageSize } },
    autoResetPageIndex: true,
  });

  if (isError) {
    return <p className="text-sm text-red-400">{t("history.loadError")}</p>;
  }

  const rows = table.getRowModel().rows;
  const { pageIndex, pageSize: size } = table.getState().pagination;
  const pageCount = table.getPageCount();
  const total = table.getFilteredRowModel().rows.length;

  return (
    <div>
      {searchPlaceholder !== undefined && (
        <input
          value={globalFilter}
          onChange={(e) => setGlobalFilter(e.target.value)}
          placeholder={searchPlaceholder}
          className="mb-2 w-64 rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-200 placeholder:text-slate-600 focus:border-slate-500 focus:outline-none"
        />
      )}

      <div className="max-h-[calc(100vh-22rem)] overflow-auto rounded-lg border border-slate-800">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 z-20 bg-slate-900 text-slate-400">
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((header) => (
                  <th
                    key={header.id}
                    onClick={header.column.getToggleSortingHandler()}
                    className="cursor-pointer select-none whitespace-nowrap bg-slate-900 px-3 py-2 font-medium hover:text-slate-200"
                  >
                    {flexRender(
                      header.column.columnDef.header,
                      header.getContext()
                    )}
                    <span className="ml-1 text-slate-500">
                      {{ asc: "▲", desc: "▼" }[
                        header.column.getIsSorted() as string
                      ] ?? ""}
                    </span>
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td
                  colSpan={columns.length}
                  className="px-3 py-6 text-center text-slate-500"
                >
                  {t("history.loading")}
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td
                  colSpan={columns.length}
                  className="h-40 px-3 py-6 text-center align-middle text-slate-500"
                >
                  {emptyText ?? t("history.empty")}
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={row.id} className="border-t border-slate-800/60">
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="px-3 py-1.5 whitespace-nowrap">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-400">
        <button
          onClick={() => table.firstPage()}
          disabled={!table.getCanPreviousPage()}
          className="rounded border border-slate-700 px-2 py-1 disabled:opacity-40"
        >
          {t("history.first")}
        </button>
        <button
          onClick={() => table.previousPage()}
          disabled={!table.getCanPreviousPage()}
          className="rounded border border-slate-700 px-2 py-1 disabled:opacity-40"
        >
          {t("history.prev")}
        </button>
        <button
          onClick={() => table.nextPage()}
          disabled={!table.getCanNextPage()}
          className="rounded border border-slate-700 px-2 py-1 disabled:opacity-40"
        >
          {t("history.next")}
        </button>
        <button
          onClick={() => table.lastPage()}
          disabled={!table.getCanNextPage()}
          className="rounded border border-slate-700 px-2 py-1 disabled:opacity-40"
        >
          {t("history.last")}
        </button>

        <span className="ml-2">
          {t("history.pageOf", {
            page: pageCount === 0 ? 0 : pageIndex + 1,
            count: pageCount,
          })}
        </span>

        <select
          value={size}
          onChange={(e) => table.setPageSize(Number(e.target.value))}
          className="ml-2 rounded border border-slate-700 bg-slate-950 px-1.5 py-1 text-slate-200 focus:border-slate-500 focus:outline-none"
        >
          {[10, 25, 50, 100].map((n) => (
            <option key={n} value={n}>
              {t("history.perPage", { n })}
            </option>
          ))}
        </select>

        <span className="ml-auto text-slate-500">
          {t("history.total", { n: total })}
        </span>
      </div>
    </div>
  );
}
