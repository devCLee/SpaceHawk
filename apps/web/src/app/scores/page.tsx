"use client";

// 위협 점수 (composite threat scoring, mentoring #11 / S2) — full-page
// dashboard: KPI tiles (population + per-method signal counts) over a ranked
// client-side DataTable of per-object composite scores with their per-method
// component breakdown. One fetch serves both. AuthGuard only gates the shell —
// the engine's MANEUVER_INTEL gate re-authorizes the call, and a denied/offline
// engine comes back `available: false` → graceful unavailable state.

import AuthGuard from "@/app/Components/guards/AuthGuard";
import { Spinner } from "@/app/Components/ui/Spinner";
import { useApiQuery } from "@/lib/api/useApiQuery";
import { queryKeys } from "@/lib/api/queryKeys";
import type {
  ScoreHistoryPoint,
  ScoresHistoryResult,
  ScoresResult,
} from "@/lib/orbital-engine";
import { t } from "@/lib/i18n/t";
import DataTable from "../history/DataTable";
import { LEVEL_CLASS, scoreColumns } from "./columns";

const WINDOW_DAYS = 30;
const LIMIT = 1000;
const STALE_MS = 60_000;

const LEVELS = ["Critical", "High", "Medium", "Low"] as const;

// SVG fill colors for the severity pie — hex twins of LEVEL_CLASS (Tailwind 400s).
const LEVEL_HEX: Record<string, string> = {
  Critical: "#f87171",
  High: "#fb923c",
  Medium: "#fbbf24",
  Low: "#34d399",
};

/** SVG path for a unit-circle pie slice spanning [startFrac, endFrac) of the
 * whole, starting at 12 o'clock and sweeping clockwise. */
function pieSlicePath(startFrac: number, endFrac: number): string {
  const a0 = 2 * Math.PI * startFrac - Math.PI / 2;
  const a1 = 2 * Math.PI * endFrac - Math.PI / 2;
  const large = endFrac - startFrac > 0.5 ? 1 : 0;
  return (
    `M 0 0 L ${Math.cos(a0)} ${Math.sin(a0)} ` +
    `A 1 1 0 ${large} 1 ${Math.cos(a1)} ${Math.sin(a1)} Z`
  );
}

/** Per-level count lines over the last N days, sharing the pie's colors.
 * Linear scale to the global max; stroke width survives the stretch via
 * non-scaling strokes. */
function SeverityTrend({ points }: { points: ScoreHistoryPoint[] }) {
  if (points.length < 2) return null;
  const max = Math.max(
    1,
    ...points.flatMap((p) => LEVELS.map((lvl) => p.by_level[lvl] ?? 0))
  );
  const W = 320;
  const H = 128;
  const PAD = 2;
  const x = (i: number) => PAD + (i * (W - 2 * PAD)) / (points.length - 1);
  const y = (n: number) => H - PAD - ((H - 2 * PAD) * n) / max;
  const axis = "#334155";
  const grid = "#1e293b";
  // Axis text lives in HTML — the SVG is stretch-scaled (preserveAspectRatio
  // "none"), which would distort glyphs.
  return (
    <div className="min-w-0 flex-1">
      <div className="flex gap-1.5">
        <div className="flex h-32 flex-col justify-between text-right text-[10px] leading-none text-slate-500">
          <span>{max}</span>
          <span>{Math.round(max / 2)}</span>
          <span>0</span>
        </div>
        <svg
          viewBox={`0 0 ${W} ${H}`}
          preserveAspectRatio="none"
          className="h-32 w-full"
          role="img"
          aria-label={`위협 등급별 ${points.length}일 추이, 최대 ${max}`}
        >
          {/* y axis, mid gridline, x axis */}
          <line
            x1={PAD}
            y1={y(max)}
            x2={PAD}
            y2={y(0)}
            stroke={axis}
            vectorEffect="non-scaling-stroke"
          />
          <line
            x1={PAD}
            y1={y(max / 2)}
            x2={W - PAD}
            y2={y(max / 2)}
            stroke={grid}
            vectorEffect="non-scaling-stroke"
          />
          <line
            x1={PAD}
            y1={y(0)}
            x2={W - PAD}
            y2={y(0)}
            stroke={axis}
            vectorEffect="non-scaling-stroke"
          />
          {LEVELS.map((lvl) => (
            <polyline
              key={lvl}
              points={points
                .map((p, i) => `${x(i)},${y(p.by_level[lvl] ?? 0)}`)
                .join(" ")}
              fill="none"
              stroke={LEVEL_HEX[lvl]}
              strokeWidth="2"
              strokeLinejoin="round"
              strokeLinecap="round"
              vectorEffect="non-scaling-stroke"
            >
              <title>{lvl}</title>
            </polyline>
          ))}
        </svg>
      </div>
      <div className="mt-1 flex justify-between pl-6 text-[10px] text-slate-500">
        <span>{points[0].date}</span>
        <span>{points[Math.floor((points.length - 1) / 2)].date}</span>
        <span>{points[points.length - 1].date}</span>
      </div>
    </div>
  );
}

/** Threat-level share of the scored population as a pie + side legend.
 * Exact counts stay in the tiles above; slice tooltips carry count + percent. */
function SeverityPie({ byLevel }: { byLevel: Record<string, number> }) {
  const total = LEVELS.reduce((sum, lvl) => sum + (byLevel[lvl] ?? 0), 0);
  if (total === 0) return null;
  const present = LEVELS.filter((lvl) => (byLevel[lvl] ?? 0) > 0);
  const slices = present.map((lvl, i) => {
    const before = present
      .slice(0, i)
      .reduce((sum, l) => sum + byLevel[l], 0);
    return {
      lvl,
      count: byLevel[lvl],
      start: before / total,
      end: (before + byLevel[lvl]) / total,
    };
  });
  const pct = (lvl: string) => ((100 * (byLevel[lvl] ?? 0)) / total).toFixed(1);
  return (
    <div className="flex shrink-0 items-center gap-8">
      <svg
        viewBox="-1.02 -1.02 2.04 2.04"
        className="h-36 w-36 shrink-0"
        role="img"
        aria-label={LEVELS.map((lvl) => `${lvl} ${byLevel[lvl] ?? 0}`).join(", ")}
      >
        {slices.length === 1 ? (
          <circle r="1" fill={LEVEL_HEX[slices[0].lvl]}>
            <title>{`${slices[0].lvl} ${slices[0].count} (100.0%)`}</title>
          </circle>
        ) : (
          slices.map((s) => (
            <path key={s.lvl} d={pieSlicePath(s.start, s.end)} fill={LEVEL_HEX[s.lvl]}>
              <title>{`${s.lvl} ${s.count} (${pct(s.lvl)}%)`}</title>
            </path>
          ))
        )}
      </svg>
      <ul className="space-y-2 text-xs">
        {LEVELS.map((lvl) => (
          <li key={lvl} className="flex items-center gap-2.5">
            <span
              className="inline-block h-3.5 w-7 rounded"
              style={{ backgroundColor: LEVEL_HEX[lvl] }}
            />
            <span className="w-14 text-slate-200">{lvl}</span>
            <span className="text-slate-500">
              {byLevel[lvl] ?? 0} · {pct(lvl)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
const METHODS = [
  "maneuver",
  "conjunction",
  "rpo",
  "debris",
  "anomaly",
] as const;

function Tile({
  label,
  value,
  accent,
}: {
  label: string;
  value: number | undefined;
  accent?: string;
}) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/50 px-3 py-2">
      <div className="text-[11px] text-slate-500">{label}</div>
      <div className={`text-lg font-semibold ${accent ?? "text-slate-100"}`}>
        {value ?? "—"}
      </div>
    </div>
  );
}

function ScoreInfo({ weights }: { weights: Record<string, number> }) {
  return (
    <details className="mb-4 rounded-lg border border-slate-800 bg-slate-900/50 text-xs text-slate-400">
      <summary className="cursor-pointer select-none px-3 py-2 font-medium text-slate-300">
        {t("scores.info.title")}
      </summary>
      <div className="space-y-2 border-t border-slate-800 px-3 py-2">
        <p>{t("scores.info.formula")}</p>
        <p>
          <span className="font-medium text-slate-300">
            {t("scores.info.weights")}:
          </span>{" "}
          {METHODS.map((m, i) => (
            <span key={m}>
              {i > 0 && " · "}
              {t(`scores.method.${m}` as Parameters<typeof t>[0])}{" "}
              <span className="text-slate-200">{weights[m] ?? "—"}</span>
            </span>
          ))}
        </p>
        <div>
          <span className="font-medium text-slate-300">
            {t("scores.info.methods")}
          </span>
          <ul className="mt-1 list-inside list-disc space-y-0.5">
            {METHODS.map((m) => (
              <li key={m}>
                <span className="text-slate-300">
                  {t(`scores.method.${m}` as Parameters<typeof t>[0])}
                </span>{" "}
                — {t(`scores.info.method.${m}` as Parameters<typeof t>[0])}
              </li>
            ))}
          </ul>
        </div>
        <p>
          <span className="font-medium text-slate-300">
            {t("scores.info.levels")}:
          </span>{" "}
          <span className={LEVEL_CLASS.Critical}>Critical ≥ 70</span> {" · "}
          <span className={LEVEL_CLASS.High}>High ≥ 45</span> {" · "}
          <span className={LEVEL_CLASS.Medium}>Medium ≥ 20</span> {" · "}
          <span className={LEVEL_CLASS.Low}>Low &lt; 20</span>
        </p>
      </div>
    </details>
  );
}

function ScoresView() {
  const scores = useApiQuery<ScoresResult>({
    queryKey: queryKeys.scores(WINDOW_DAYS),
    url: "/api/scores",
    options: {
      params: { window_days: WINDOW_DAYS, limit: LIMIT },
      staleTime: STALE_MS,
    },
  });

  const history = useApiQuery<ScoresHistoryResult>({
    queryKey: queryKeys.scoresHistory(14),
    url: "/api/scores/history",
    options: {
      params: { days: 14, window_days: WINDOW_DAYS },
      staleTime: STALE_MS,
    },
  });

  const summary = scores.data?.summary;

  return (
    // The global stylesheet locks body scroll (overflow: hidden) for the globe
    // dashboard and pads body 56px for the fixed header, so this page scrolls
    // inside its own <main>, sized to the body's content box — a full 100vh
    // here would hang 56px past the viewport and clip the table pagination.
    <main className="h-[calc(100vh-56px)] overflow-y-auto bg-black text-slate-200">
      <div className="px-8 pt-8 pb-8">
        <h1 className="mb-1 text-2xl font-semibold">{t("scores.title")}</h1>
        <p className="mb-4 text-xs text-slate-500">
          {t("scores.window", {
            days: scores.data?.window_days ?? WINDOW_DAYS,
          })}
        </p>

        {scores.data?.available === false ? (
          <p className="text-sm text-slate-500">{t("history.unavailable")}</p>
        ) : (
          <>
            <ScoreInfo weights={scores.data?.weights ?? {}} />
            <div className="mb-2 grid grid-cols-2 gap-2 sm:grid-cols-5">
              <Tile label={t("scores.kpi.total")} value={summary?.total} />
              {LEVELS.map((lvl) => (
                <Tile
                  key={lvl}
                  label={lvl}
                  value={summary?.by_level?.[lvl]}
                  accent={LEVEL_CLASS[lvl]}
                />
              ))}
            </div>
            <div className="mb-2 flex items-center gap-10 rounded-lg border border-slate-800 bg-slate-900/50 p-4">
              <SeverityPie byLevel={summary?.by_level ?? {}} />
              {history.isLoading ? (
                <div className="flex h-32 min-w-0 flex-1 items-center justify-center">
                  <Spinner className="size-6 text-slate-400" />
                </div>
              ) : (
                <SeverityTrend points={history.data?.points ?? []} />
              )}
            </div>
            <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-5">
              {METHODS.map((m) => (
                <Tile
                  key={m}
                  label={t(`scores.method.${m}` as Parameters<typeof t>[0])}
                  value={summary?.by_method?.[m]}
                />
              ))}
            </div>

            <DataTable
              columns={scoreColumns}
              data={scores.data?.items}
              isLoading={scores.isLoading}
              isError={scores.isError}
              searchPlaceholder={t("history.search")}
              initialSorting={[{ id: "composite", desc: true }]}
              scrollInside={false}
            />
          </>
        )}
      </div>
    </main>
  );
}

export default function ScoresPage() {
  return (
    <AuthGuard>
      <ScoresView />
    </AuthGuard>
  );
}
