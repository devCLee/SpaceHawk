// Column definitions for the 분석 이력 tables — one ColumnDef array per tab,
// mirroring the engine response models in lib/orbital-engine.ts. Formatters
// only; all sorting/filtering is DataTable's client-side row models.

import { type ColumnDef } from "@tanstack/react-table";
import type {
  Alert,
  Conjunction,
  HistoryPoint,
  Maneuver,
  ManeuverBaseline,
} from "@/lib/orbital-engine";
import { alertStatusLabel, maneuverTypeLabel } from "@/lib/i18n/enums";
import { t } from "@/lib/i18n/t";

const dash = (v: string | null | undefined) => v ?? "—";
const num = (v: number | null | undefined, digits = 2) =>
  v == null ? "—" : v.toFixed(digits);
const dt = (v: string | null | undefined) =>
  v ? new Date(v).toLocaleString("ko-KR") : "—";
const exp = (v: number | null | undefined) =>
  v == null ? "—" : v.toExponential(2);

const SEVERITY_CLASS: Record<string, string> = {
  HIGH: "text-red-400",
  MOD: "text-amber-400",
  LOW: "text-emerald-400",
};

const severityCell = (v: string | null) =>
  v ? (
    <span className={`font-medium ${SEVERITY_CLASS[v] ?? ""}`}>{v}</span>
  ) : (
    "—"
  );

// ① 근접/충돌 — the engine only returns events whose TCA is still in the
// future (repository.query_conjunctions filters `tca >= now()`), so this tab
// lists screened/upcoming conjunctions; past-TCA rows stay in the DB unexposed.
export const conjunctionColumns: ColumnDef<Conjunction, unknown>[] = [
  {
    accessorKey: "tca",
    header: t("history.col.tca"),
    cell: ({ getValue }) => dt(getValue<string>()),
  },
  { accessorKey: "primary_name", header: t("history.col.primary") },
  { accessorKey: "secondary_name", header: t("history.col.secondary") },
  {
    accessorKey: "miss_distance_km",
    header: t("history.col.missDistance"),
    cell: ({ getValue }) => num(getValue<number>()),
  },
  {
    accessorKey: "relative_speed_km_s",
    header: t("history.col.relSpeed"),
    cell: ({ getValue }) => num(getValue<number | null>()),
  },
  {
    accessorKey: "probability",
    header: t("history.col.probability"),
    cell: ({ getValue }) => exp(getValue<number | null>()),
  },
  {
    accessorKey: "severity",
    header: t("history.col.severity"),
    cell: ({ getValue }) => severityCell(getValue<string>()),
  },
  {
    accessorKey: "source",
    header: t("history.col.source"),
    cell: ({ getValue }) => dash(getValue<string | undefined>()),
  },
  {
    accessorKey: "cdm_id",
    header: "CDM ID",
    cell: ({ getValue }) => dash(getValue<string | null>()),
  },
];

// ② 기동
export const maneuverColumns: ColumnDef<Maneuver, unknown>[] = [
  {
    accessorKey: "detected_epoch",
    header: t("history.col.detectedEpoch"),
    cell: ({ getValue }) => dt(getValue<string>()),
  },
  { accessorKey: "object_name", header: t("history.col.objectName") },
  {
    accessorKey: "norad_cat_id",
    header: "NORAD",
    cell: ({ getValue }) => getValue<number | null>() ?? "—",
  },
  {
    accessorKey: "maneuver_type",
    header: t("history.col.maneuverType"),
    cell: ({ getValue }) => maneuverTypeLabel(getValue<string>()),
  },
  {
    accessorKey: "delta_v_m_s",
    header: t("history.col.deltaV"),
    cell: ({ getValue }) => num(getValue<number | null>()),
  },
  {
    accessorKey: "delta_sma_km",
    header: t("history.col.deltaSma"),
    cell: ({ getValue }) => num(getValue<number>(), 3),
  },
  {
    accessorKey: "delta_inc_deg",
    header: t("history.col.deltaInc"),
    cell: ({ getValue }) => num(getValue<number>(), 4),
  },
  {
    accessorKey: "delta_raan_deg",
    header: t("history.col.deltaRaan"),
    cell: ({ getValue }) => num(getValue<number>(), 4),
  },
  {
    accessorKey: "confidence",
    header: t("history.col.confidence"),
    cell: ({ getValue }) => `${(getValue<number>() * 100).toFixed(0)}%`,
  },
  {
    accessorKey: "detection_statistic",
    header: t("history.col.sigma"),
    cell: ({ getValue }) => num(getValue<number>(), 1),
  },
];

// ③ 경보 (full log) — shared base for ④ RPO below.
export const alertColumns: ColumnDef<Alert, unknown>[] = [
  {
    accessorKey: "created_at",
    header: t("history.col.createdAt"),
    cell: ({ getValue }) => dt(getValue<string | null>()),
  },
  { accessorKey: "type", header: t("history.col.type") },
  {
    accessorKey: "severity",
    header: t("history.col.severity"),
    cell: ({ getValue }) => severityCell(getValue<string | null>()),
  },
  { accessorKey: "message", header: t("history.col.message") },
  {
    accessorKey: "status",
    header: t("history.col.status"),
    cell: ({ getValue }) => alertStatusLabel(getValue<string>()),
  },
  {
    accessorKey: "acknowledged_by",
    header: t("history.col.ackBy"),
    cell: ({ getValue }) => dash(getValue<string | null>()),
  },
  {
    accessorKey: "acknowledged_at",
    header: t("history.col.ackAt"),
    cell: ({ getValue }) => dt(getValue<string | null>()),
  },
];

// ④ RPO — same alert rows filtered to type='rpo'; the type column is
// redundant, the subject object is not.
export const rpoColumns: ColumnDef<Alert, unknown>[] = [
  ...alertColumns.filter(
    (c) => (c as { accessorKey?: string }).accessorKey !== "type"
  ),
  {
    accessorKey: "object_id",
    header: t("history.col.objectId"),
    cell: ({ getValue }) => dash(getValue<string | null>()),
  },
];

// ⑤ 행동 기준선 — current fingerprint snapshot per object.
export const baselineColumns: ColumnDef<ManeuverBaseline, unknown>[] = [
  { accessorKey: "object_name", header: t("history.col.objectName") },
  { accessorKey: "sample_count", header: t("history.col.sampleCount") },
  {
    accessorKey: "mean_interval_days",
    header: t("history.col.meanInterval"),
    cell: ({ getValue }) => num(getValue<number | null>(), 1),
  },
  {
    accessorKey: "interval_mad_days",
    header: t("history.col.intervalMad"),
    cell: ({ getValue }) => num(getValue<number | null>(), 1),
  },
  {
    accessorKey: "mean_delta_v_m_s",
    header: t("history.col.meanDeltaV"),
    cell: ({ getValue }) => num(getValue<number>(), 1),
  },
  {
    accessorKey: "delta_v_mad_m_s",
    header: t("history.col.deltaVMad"),
    cell: ({ getValue }) => num(getValue<number>(), 1),
  },
  {
    accessorKey: "type_distribution",
    header: t("history.col.typeDist"),
    enableSorting: false,
    cell: ({ getValue }) =>
      Object.entries(getValue<Record<string, number>>() ?? {})
        .map(([ty, n]) => `${maneuverTypeLabel(ty)}×${n}`)
        .join(" · ") || "—",
  },
  {
    accessorKey: "last_epoch",
    header: t("history.col.lastEpoch"),
    cell: ({ getValue }) => dt(getValue<string>()),
  },
  {
    accessorKey: "updated_at",
    header: t("history.col.updatedAt"),
    cell: ({ getValue }) => dt(getValue<string | null>()),
  },
];

// ⑥ 궤도 이력 — one object's gp_history element sets.
export const historyPointColumns: ColumnDef<HistoryPoint, unknown>[] = [
  {
    accessorKey: "epoch",
    header: t("history.col.epoch"),
    cell: ({ getValue }) => dt(getValue<string>()),
  },
  {
    accessorKey: "data_source",
    header: t("history.col.dataSource"),
    cell: ({ getValue }) => dash(getValue<string | null>()),
  },
  {
    accessorKey: "semimajor_axis_km",
    header: t("history.col.sma"),
    cell: ({ getValue }) => num(getValue<number | null>()),
  },
  {
    accessorKey: "eccentricity",
    header: t("history.col.ecc"),
    cell: ({ getValue }) => num(getValue<number | null>(), 6),
  },
  {
    accessorKey: "inclination",
    header: t("history.col.inc"),
    cell: ({ getValue }) => num(getValue<number | null>(), 4),
  },
  {
    accessorKey: "ra_of_asc_node",
    header: t("history.col.raan"),
    cell: ({ getValue }) => num(getValue<number | null>(), 4),
  },
  {
    accessorKey: "arg_of_pericenter",
    header: t("history.col.argp"),
    cell: ({ getValue }) => num(getValue<number | null>(), 4),
  },
  {
    accessorKey: "mean_anomaly",
    header: t("history.col.meanAnomaly"),
    cell: ({ getValue }) => num(getValue<number | null>(), 4),
  },
  {
    accessorKey: "period_min",
    header: t("history.col.period"),
    cell: ({ getValue }) => num(getValue<number | null>()),
  },
  {
    accessorKey: "apoapsis_km",
    header: t("history.col.apoapsis"),
    cell: ({ getValue }) => num(getValue<number | null>(), 1),
  },
  {
    accessorKey: "periapsis_km",
    header: t("history.col.periapsis"),
    cell: ({ getValue }) => num(getValue<number | null>(), 1),
  },
  {
    accessorKey: "bstar",
    header: t("history.col.bstar"),
    cell: ({ getValue }) => exp(getValue<number | null>()),
  },
];
