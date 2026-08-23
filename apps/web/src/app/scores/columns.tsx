// Column definitions for the 위협 점수 dashboard — composite + per-method
// component scores, mirroring the engine's ScoreItem (lib/orbital-engine.ts).
// Formatters only; sorting/filtering is DataTable's client-side row models.
// Component cells carry the raw evidence in `title` for hover drill-down.

import { type ColumnDef } from "@tanstack/react-table";
import type { ScoreItem } from "@/lib/orbital-engine";
import { t } from "@/lib/i18n/t";

const num = (v: number | null | undefined, digits = 2) =>
  v == null ? "—" : v.toFixed(digits);
const exp = (v: number | null | undefined) =>
  v == null ? "—" : v.toExponential(2);

/** Threat-level coloring — history's SEVERITY_CLASS idiom over the debris
 * Low/Medium/High/Critical vocabulary the composite score reuses. */
export const LEVEL_CLASS: Record<string, string> = {
  Critical: "text-red-400",
  High: "text-orange-400",
  Medium: "text-amber-400",
  Low: "text-emerald-400",
};

const componentCell = (value: number | null, title: string) =>
  value == null ? "—" : <span title={title}>{value.toFixed(2)}</span>;

export const scoreColumns: ColumnDef<ScoreItem, unknown>[] = [
  { accessorKey: "object_name", header: t("history.col.objectName") },
  {
    accessorKey: "composite",
    header: t("scores.col.composite"),
    cell: ({ row }) => (
      <span
        className={`font-semibold ${LEVEL_CLASS[row.original.level] ?? ""}`}
      >
        {row.original.composite.toFixed(1)}
      </span>
    ),
  },
  {
    accessorKey: "level",
    header: t("scores.col.level"),
    cell: ({ getValue }) => {
      const v = getValue<string>();
      return <span className={`font-medium ${LEVEL_CLASS[v] ?? ""}`}>{v}</span>;
    },
  },
  {
    id: "maneuver",
    accessorFn: (r) => r.components.maneuver,
    header: t("scores.method.maneuver"),
    cell: ({ row }) =>
      componentCell(
        row.original.components.maneuver,
        `Δv ${num(row.original.raw.max_delta_v_m_s)} m/s · n=${row.original.raw.maneuver_count ?? 0}`
      ),
  },
  {
    id: "conjunction",
    accessorFn: (r) => r.components.conjunction,
    header: t("scores.method.conjunction"),
    cell: ({ row }) =>
      componentCell(
        row.original.components.conjunction,
        `Pc ${exp(row.original.raw.max_pc)} · ${num(row.original.raw.min_miss_km)} km · n=${row.original.raw.conjunction_count ?? 0}`
      ),
  },
  {
    id: "rpo",
    accessorFn: (r) => r.components.rpo,
    header: t("scores.method.rpo"),
    cell: ({ row }) =>
      componentCell(
        row.original.components.rpo,
        `coplanarity ${num(row.original.raw.max_coplanarity)} · n=${row.original.raw.rpo_count ?? 0}`
      ),
  },
  {
    id: "debris",
    accessorFn: (r) => r.components.debris,
    header: t("scores.method.debris"),
    cell: ({ row }) =>
      componentCell(
        row.original.components.debris,
        `risk ${num(row.original.raw.debris_risk_score, 1)} / 100`
      ),
  },
  {
    id: "anomaly",
    accessorFn: (r) => r.components.anomaly,
    header: t("scores.method.anomaly"),
    cell: ({ row }) =>
      componentCell(
        row.original.components.anomaly,
        `σ ${num(row.original.raw.max_delta_v_sigma)}${row.original.raw.novel_type ? " · novel type" : ""} · n=${row.original.raw.anomaly_count ?? 0}`
      ),
  },
];
