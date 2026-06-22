"use client";

// 2D geographic (longitude × latitude) debris-density heatmap — lives INSIDE the
// left control rail (rendered by DebrisPanel), toggled via DebrisLayerContext.heatmap.
// The tracked debris are propagated in the shared worker, binned into a lon×lat
// grid, risk-weighted, smoothed, and drawn on an equirectangular canvas with
// labelled X (longitude) / Y (latitude) axes + titles and a heat ramp. Clicking a
// cell marks it and opens a popup with that field's lon/lat range, debris count,
// and risk breakdown.

import React from "react";
import { useDebris } from "@/lib/api/useDebris";
import { useDebrisLayer } from "../context/DebrisLayerContext";
import {
  RISK_ORDER,
  RISK_WEIGHT,
  RISK_LABEL_KEY,
  riskColor,
  type DebrisRiskLevel,
} from "../data/debrisRisk";
import { t } from "@/lib/i18n/t";

const GRID_W = 144; // 2.5° longitude bins
const GRID_H = 72; // 2.5° latitude bins
const DEG = 360 / GRID_W; // = 2.5° (longitude bin width)
const LAT_DEG = 180 / GRID_H; // = 2.5° (latitude bin width; matches the worker's gy binning)

// Canvas = plot area + axis margins (sized to fit the ~280px rail panel body).
const MARGIN_LEFT = 30;
const MARGIN_RIGHT = 6;
const MARGIN_TOP = 6;
const MARGIN_BOTTOM = 26;
const PLOT_W = 224;
const PLOT_H = 112;
const CANVAS_W = MARGIN_LEFT + PLOT_W + MARGIN_RIGHT; // 260
const CANVAS_H = MARGIN_TOP + PLOT_H + MARGIN_BOTTOM; // 144
const POPUP_W = 148;
const POPUP_H = 72; // popup is clamped within the canvas so it can't overlap the legend

const LON_TICKS = [-180, -90, 0, 90, 180];
const LAT_TICKS = [90, 45, 0, -45, -90];

// Heat ramp stops [position, r, g, b]: blue → cyan → green → yellow → orange → red.
const HEAT_STOPS: ReadonlyArray<readonly [number, number, number, number]> = [
  [0.0, 30, 60, 160],
  [0.25, 0, 200, 220],
  [0.5, 40, 210, 90],
  [0.7, 240, 220, 60],
  [0.85, 245, 150, 40],
  [1.0, 239, 68, 68],
];

const LEGEND_GRADIENT = `linear-gradient(to right, ${HEAT_STOPS.map(
  ([, r, g, b]) => `rgb(${r},${g},${b})`
).join(", ")})`;

/** Map a normalized density [0,1] to an [r,g,b,a] heat colour (alpha fades in). */
function heatColor(t01: number): [number, number, number, number] {
  let lo = HEAT_STOPS[0];
  let hi = HEAT_STOPS[HEAT_STOPS.length - 1];
  for (let i = 0; i < HEAT_STOPS.length - 1; i++) {
    if (t01 >= HEAT_STOPS[i][0] && t01 <= HEAT_STOPS[i + 1][0]) {
      lo = HEAT_STOPS[i];
      hi = HEAT_STOPS[i + 1];
      break;
    }
  }
  const span = hi[0] - lo[0] || 1;
  const f = (t01 - lo[0]) / span;
  return [
    Math.round(lo[1] + (hi[1] - lo[1]) * f),
    Math.round(lo[2] + (hi[2] - lo[2]) * f),
    Math.round(lo[3] + (hi[3] - lo[3]) * f),
    Math.round(255 * Math.min(1, 0.15 + 0.85 * t01)),
  ];
}

type ZeroLevels = Record<DebrisRiskLevel, number>;
const zeroLevels = (): ZeroLevels => ({ Critical: 0, High: 0, Medium: 0, Low: 0 });

interface CellInfo {
  count: number;
  byLevel: ZeroLevels;
  names: string[];
}

interface Selected {
  ix: number;
  iy: number;
}

export const DebrisHeatmap2D: React.FunctionComponent = () => {
  const { heatmap, setHeatmap } = useDebrisLayer();
  const { data: debris } = useDebris();
  const canvasRef = React.useRef<HTMLCanvasElement>(null);
  const [grid, setGrid] = React.useState<Float32Array | null>(null);
  const [cells, setCells] = React.useState<Map<number, CellInfo>>(
    () => new Map()
  );
  const [selected, setSelected] = React.useState<Selected | null>(null);

  // Build the risk-weighted density grid + per-cell info from current debris
  // positions, computed in the propagation worker (one-shot per open). Each object
  // is splatted 3×3 into the draw grid (smoothing) and counted in its exact cell
  // (for the click popup). Worker torn down on close/unmount.
  React.useEffect(() => {
    if (!heatmap || !debris || debris.length === 0) return;
    const usable = debris.filter((d) => d.tle_line1 && d.tle_line2);
    const inputs = usable.map((d) => ({
      line1: d.tle_line1 as string,
      line2: d.tle_line2 as string,
    }));

    let worker: Worker | null = null;
    try {
      worker = new Worker(
        new URL("../workers/propagation.worker.ts", import.meta.url)
      );
      worker.onmessage = (e: MessageEvent) => {
        const data = e.data as {
          type: string;
          lon: Float64Array;
          lat: Float64Array;
        };
        if (data.type !== "positions") return;
        const g = new Float32Array(GRID_W * GRID_H);
        const cellMap = new Map<number, CellInfo>();
        for (let i = 0; i < data.lon.length; i++) {
          const lon = data.lon[i];
          const lat = data.lat[i];
          if (Number.isNaN(lon) || Number.isNaN(lat)) continue;
          const d = usable[i];
          const level = (d.risk_level as DebrisRiskLevel) ?? "Low";
          const w = RISK_WEIGHT[level] ?? 0.3;
          const gx = Math.min(
            GRID_W - 1,
            Math.max(0, Math.floor(((lon + 180) / 360) * GRID_W))
          );
          const gy = Math.min(
            GRID_H - 1,
            Math.max(0, Math.floor(((90 - lat) / 180) * GRID_H))
          );
          // Smoothed draw grid (3×3 splat, longitude wraps).
          for (let dy = -1; dy <= 1; dy++) {
            const y = gy + dy;
            if (y < 0 || y >= GRID_H) continue;
            for (let dx = -1; dx <= 1; dx++) {
              const x = (gx + dx + GRID_W) % GRID_W;
              g[y * GRID_W + x] += w * (dx === 0 && dy === 0 ? 1 : 0.5);
            }
          }
          // Exact-cell info for the click popup.
          const key = gy * GRID_W + gx;
          let info = cellMap.get(key);
          if (info === undefined) {
            info = { count: 0, byLevel: zeroLevels(), names: [] };
            cellMap.set(key, info);
          }
          info.count += 1;
          info.byLevel[level] += 1;
          if (info.names.length < 5) info.names.push(d.object_name);
        }
        setCells(cellMap);
        setSelected(null); // a fresh grid invalidates any open popup
        setGrid(g);
      };
      worker.postMessage({ type: "init", sats: inputs });
      worker.postMessage({ type: "propagate", timeMs: Date.now() });
    } catch {
      worker = null;
    }

    return () => {
      if (worker) {
        worker.onmessage = null;
        worker.terminate();
      }
    };
  }, [heatmap, debris]);

  // Draw the grid → heat ramp scaled into the plot area, plus axes (ticks +
  // titles), graticule, and the selected-cell marker.
  React.useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || grid === null) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let max = 0;
    for (let i = 0; i < grid.length; i++) if (grid[i] > max) max = grid[i];
    const norm = max > 0 ? 1 / max : 0;

    const img = ctx.createImageData(GRID_W, GRID_H);
    for (let i = 0; i < grid.length; i++) {
      if (grid[i] <= 0) continue;
      const tval = Math.min(1, Math.sqrt(grid[i] * norm)); // sqrt lifts low density
      const [r, g, b, a] = heatColor(tval);
      img.data[i * 4] = r;
      img.data[i * 4 + 1] = g;
      img.data[i * 4 + 2] = b;
      img.data[i * 4 + 3] = a;
    }
    const off = document.createElement("canvas");
    off.width = GRID_W;
    off.height = GRID_H;
    off.getContext("2d")?.putImageData(img, 0, 0);

    ctx.clearRect(0, 0, CANVAS_W, CANVAS_H);
    // Plot background.
    ctx.fillStyle = "#0a0f1a";
    ctx.fillRect(MARGIN_LEFT, MARGIN_TOP, PLOT_W, PLOT_H);
    ctx.imageSmoothingEnabled = true;
    ctx.drawImage(off, MARGIN_LEFT, MARGIN_TOP, PLOT_W, PLOT_H);

    // Graticule.
    ctx.strokeStyle = "rgba(255,255,255,0.12)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (const lat of LAT_TICKS) {
      const y = MARGIN_TOP + ((90 - lat) / 180) * PLOT_H;
      ctx.moveTo(MARGIN_LEFT, y);
      ctx.lineTo(MARGIN_LEFT + PLOT_W, y);
    }
    for (const lon of LON_TICKS) {
      const x = MARGIN_LEFT + ((lon + 180) / 360) * PLOT_W;
      ctx.moveTo(x, MARGIN_TOP);
      ctx.lineTo(x, MARGIN_TOP + PLOT_H);
    }
    ctx.stroke();
    // Plot border.
    ctx.strokeStyle = "rgba(255,255,255,0.25)";
    ctx.strokeRect(MARGIN_LEFT, MARGIN_TOP, PLOT_W, PLOT_H);

    // Axis tick labels.
    ctx.fillStyle = "#7d8da0";
    ctx.font = "9px system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    for (const lon of LON_TICKS) {
      const x = MARGIN_LEFT + ((lon + 180) / 360) * PLOT_W;
      ctx.fillText(`${lon}`, x, MARGIN_TOP + PLOT_H + 3);
    }
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    for (const lat of LAT_TICKS) {
      const y = MARGIN_TOP + ((90 - lat) / 180) * PLOT_H;
      ctx.fillText(`${lat}`, MARGIN_LEFT - 4, y);
    }

    // Axis titles.
    ctx.fillStyle = "#9aa7b4";
    ctx.font = "10px system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "bottom";
    ctx.fillText(t("debris.heatmap.xaxis"), MARGIN_LEFT + PLOT_W / 2, CANVAS_H);
    ctx.save();
    ctx.translate(9, MARGIN_TOP + PLOT_H / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.textBaseline = "top";
    ctx.fillText(t("debris.heatmap.yaxis"), 0, 0);
    ctx.restore();

    // Selected-cell marker (a small ring — single cells are sub-pixel).
    if (selected) {
      const cx = MARGIN_LEFT + ((selected.ix + 0.5) / GRID_W) * PLOT_W;
      const cy = MARGIN_TOP + ((selected.iy + 0.5) / GRID_H) * PLOT_H;
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.arc(cx, cy, 5, 0, 2 * Math.PI);
      ctx.stroke();
    }
  }, [grid, selected]);

  const onCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas || grid === null) return;
    const rect = canvas.getBoundingClientRect();
    const sx = (e.clientX - rect.left) * (canvas.width / rect.width);
    const sy = (e.clientY - rect.top) * (canvas.height / rect.height);
    const px = sx - MARGIN_LEFT;
    const py = sy - MARGIN_TOP;
    if (px < 0 || px > PLOT_W || py < 0 || py > PLOT_H) {
      setSelected(null); // click outside the plot dismisses the popup
      return;
    }
    const ix = Math.min(GRID_W - 1, Math.max(0, Math.floor((px / PLOT_W) * GRID_W)));
    const iy = Math.min(GRID_H - 1, Math.max(0, Math.floor((py / PLOT_H) * GRID_H)));
    setSelected({ ix, iy });
  };

  if (!heatmap) return null;

  // Popup placement + content for the selected cell.
  let popup: React.ReactNode = null;
  if (selected) {
    const info = cells.get(selected.iy * GRID_W + selected.ix);
    const lonLo = -180 + selected.ix * DEG;
    const latHi = 90 - selected.iy * LAT_DEG;
    const left = Math.min(
      CANVAS_W - POPUP_W - 4,
      MARGIN_LEFT + ((selected.ix + 0.5) / GRID_W) * PLOT_W + 8
    );
    const top = Math.min(
      CANVAS_H - POPUP_H,
      Math.max(0, MARGIN_TOP + ((selected.iy + 0.5) / GRID_H) * PLOT_H - 10)
    );
    popup = (
      <div style={{ ...styles.popup, left: Math.max(4, left), top }}>
        <div style={styles.popupHead}>
          <span style={styles.popupCoord}>
            {lonLo}°~{lonLo + DEG}° · {latHi - LAT_DEG}°~{latHi}°
          </span>
          <button
            type="button"
            aria-label={t("debris.heatmap.popupClose")}
            onClick={() => setSelected(null)}
            style={styles.popupClose}
          >
            ✕
          </button>
        </div>
        {info ? (
          <>
            <div style={styles.popupCount}>
              {t("debris.heatmap.cellCount", { n: info.count })}
            </div>
            <div style={styles.popupChips}>
              {RISK_ORDER.map((level) => (
                <span
                  key={level}
                  style={styles.popupChip}
                  aria-label={t(RISK_LABEL_KEY[level])}
                >
                  <span
                    style={{ ...styles.popupSwatch, background: riskColor(level) }}
                  />
                  {info.byLevel[level]}
                </span>
              ))}
            </div>
          </>
        ) : (
          <div style={styles.popupCount}>{t("debris.heatmap.cellEmpty")}</div>
        )}
      </div>
    );
  }

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <span style={styles.title}>{t("debris.heatmap.title")}</span>
        <button
          type="button"
          aria-label={t("debris.heatmap.close")}
          onClick={() => setHeatmap(false)}
          style={styles.close}
        >
          ✕
        </button>
      </div>
      <div style={{ position: "relative", width: CANVAS_W }}>
        <canvas
          ref={canvasRef}
          width={CANVAS_W}
          height={CANVAS_H}
          onClick={onCanvasClick}
          style={styles.canvas}
        />
        {popup}
      </div>
      <div style={styles.legend}>
        <span style={styles.legendLabel}>{t("debris.heatmap.low")}</span>
        <span style={styles.legendBar} />
        <span style={styles.legendLabel}>{t("debris.heatmap.high")}</span>
      </div>
    </div>
  );
};

export default DebrisHeatmap2D;

const styles: Record<string, React.CSSProperties> = {
  container: {
    marginTop: 4,
    display: "flex",
    flexDirection: "column",
    gap: 4,
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
  },
  title: { fontSize: 11, color: "#7d8da0" },
  close: {
    border: "none",
    background: "transparent",
    color: "#9aa7b4",
    fontSize: 13,
    cursor: "pointer",
    padding: 2,
  },
  canvas: {
    width: CANVAS_W,
    height: CANVAS_H,
    display: "block",
    borderRadius: 4,
    cursor: "crosshair",
  },
  legend: { display: "flex", alignItems: "center", gap: 6 },
  legendLabel: { fontSize: 11, color: "#7d8da0" },
  legendBar: {
    flex: 1,
    height: 8,
    borderRadius: 2,
    background: LEGEND_GRADIENT,
    border: "1px solid rgba(255,255,255,0.15)",
  },
  popup: {
    position: "absolute",
    width: POPUP_W,
    padding: "6px 8px",
    background: "rgba(8, 12, 20, 0.96)",
    border: "1px solid rgba(255,255,255,0.2)",
    borderRadius: 5,
    boxShadow: "0 4px 14px rgba(0,0,0,0.4)",
    pointerEvents: "auto",
    zIndex: 1,
  },
  popupHead: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 6,
    marginBottom: 4,
  },
  popupCoord: {
    fontSize: 10,
    color: "#cfd8e3",
    fontVariantNumeric: "tabular-nums",
  },
  popupClose: {
    border: "none",
    background: "transparent",
    color: "#9aa7b4",
    fontSize: 12,
    cursor: "pointer",
    padding: 0,
    lineHeight: 1,
  },
  popupCount: { fontSize: 11, color: "#e6edf3", marginBottom: 4 },
  popupChips: { display: "flex", gap: 8 },
  popupChip: {
    display: "flex",
    alignItems: "center",
    gap: 3,
    fontSize: 11,
    color: "#cfd8e3",
    fontVariantNumeric: "tabular-nums",
  },
  popupSwatch: {
    width: 9,
    height: 9,
    borderRadius: 2,
    border: "1px solid rgba(255,255,255,0.25)",
  },
};
