"use client";

import React from "react";
import type { CesiumType } from "../types/cesium";
import {
  Cesium3DTileset,
  type Entity,
  type PointPrimitive,
  type PointPrimitiveCollection,
  type ScreenSpaceEventHandler,
  type Viewer,
} from "cesium";
import {
  twoline2satrec,
  propagate,
  gstime,
  eciToGeodetic,
  degreesLat,
  degreesLong,
  type SatRec,
} from "satellite.js";
import type { Position } from "../types/position";
import type { TleObject } from "../utils/sgp4FromTle";
import { useSelectedSatellite } from "../context/SelectedSatelliteContext";
import { useCatalogView } from "../context/CatalogViewContext";
import { useSensor } from "../context/SensorContext";
import { classifyConstellation } from "../data/constellations";
import { toast } from "sonner";
//NOTE: This is required to get the stylings for default Cesium UI and controls
import "cesium/Build/Cesium/Widgets/widgets.css";

//NOTE: This is required for cpx/Next 16
if (typeof window !== "undefined") {
  (window as any).CESIUM_BASE_URL = "/cesium";
}

/** One orbit period in seconds (LEO ~90 min). */
const ORBIT_PERIOD_SEC = 90 * 60;
/** How far before/after "now" the selected object's orbit line is sampled. */
const ORBIT_WINDOW_SEC = ORBIT_PERIOD_SEC;
/** Sample step for the selected orbit polyline. */
const ORBIT_SAMPLE_STEP_SEC = 20;
/** How often (sim seconds) the full catalog's point positions are re-propagated. */
const POSITION_UPDATE_SEC = 1;

const POINT_SIZE = 3;
const SELECTED_POINT_SIZE = 10;
const WATCHED_POINT_SIZE = 6;
const MATCH_POINT_SIZE = 4;

/**
 * Globe data source:
 * - "offline": Cesium's bundled Natural Earth II imagery (copied into
 *   /cesium/Assets) + the default ellipsoid. No Cesium Ion, no network — works
 *   in an air-gapped enclave and requires no token.
 * - "online": Cesium Ion world imagery + world terrain + OSM Buildings. Requires
 *   NEXT_PUBLIC_CESIUM_TOKEN and internet access.
 */
type GlobeMode = "offline" | "online";

/** A parsed catalog object: SGP4 record + its GPU point + identity. */
interface RenderedSat {
  id: string;
  name: string;
  satrec: SatRec;
  primitive: PointPrimitive;
  countryCode: string | null;
  constellation: string | null;
}

/** Default Cesium widgets to hide — keep timeline/animation (time control) and
 * the scene-mode picker (2D/3D toggle); drop the rest of the chrome. */
const HIDDEN_WIDGETS = {
  homeButton: false,
  navigationHelpButton: false,
  fullscreenButton: false,
  geocoder: false,
  infoBox: false,
  selectionIndicator: false,
} as const;

/** TEME (ECI km) -> geodetic lat/lon/alt(m) at `date`, or null if SGP4 fails. */
function geodeticAt(
  satrec: SatRec,
  date: Date
): { lat: number; lon: number; altM: number } | null {
  const pv = propagate(satrec, date);
  if (pv === null || pv.position == null) return null;
  const gd = eciToGeodetic(pv.position, gstime(date));
  return {
    lat: degreesLat(gd.latitude),
    lon: degreesLong(gd.longitude),
    altM: gd.height * 1000,
  };
}

export const CesiumComponent: React.FunctionComponent<{
  CesiumJs: CesiumType;
  positions: Position[];
  tleEntries?: TleObject[];
}> = ({ CesiumJs, positions, tleEntries }) => {
  const cesiumViewer = React.useRef<Viewer | null>(null);
  const cesiumContainerRef = React.useRef<HTMLDivElement>(null);
  const addedScenePrimitives = React.useRef<Cesium3DTileset[]>([]);
  const pointsRef = React.useRef<PointPrimitiveCollection | null>(null);
  const satsByIdRef = React.useRef<Map<string, RenderedSat>>(new Map());
  const pickHandlerRef = React.useRef<ScreenSpaceEventHandler | null>(null);
  const selectedOrbitRef = React.useRef<Entity | null>(null);
  const sensorEntityRef = React.useRef<Entity | null>(null);
  const [isLoaded, setIsLoaded] = React.useState(false);
  // Default to the online (Cesium Ion) globe; fall back to the bundled offline
  // imagery only when the browser reports no network connection. This client-
  // only component (CesiumWrapper loads it ssr:false) so `navigator` is safe.
  const [mode, setMode] = React.useState<GlobeMode>(() =>
    typeof navigator !== "undefined" && navigator.onLine === false
      ? "offline"
      : "online"
  );

  // On first mount, if there is no network, tell the user why they're seeing the
  // offline globe. Fires once — manual switches afterward are intentional.
  React.useEffect(() => {
    if (typeof navigator !== "undefined" && navigator.onLine === false) {
      toast.warning("No network connection detected — loading the offline globe.");
    }
  }, []);
  const { selectedId, setSelectedId } = useSelectedSatellite();
  const { countryFilter, constellationFilter, watchlist } = useCatalogView();
  const { activeSensor } = useSensor();

  // (Re)create the Cesium viewer whenever the globe mode changes. The imagery /
  // terrain providers are chosen at construction time, so switching mode rebuilds
  // the viewer. Satellites re-render via the `isLoaded` effect below.
  React.useEffect(() => {
    if (cesiumContainerRef.current === null) return;

    // Tear down any existing viewer (mode switch / React strict-mode remount).
    if (cesiumViewer.current !== null && !cesiumViewer.current.isDestroyed()) {
      cesiumViewer.current.destroy();
    }
    cesiumViewer.current = null;
    addedScenePrimitives.current = [];
    pointsRef.current = null;
    satsByIdRef.current = new Map();
    selectedOrbitRef.current = null;
    sensorEntityRef.current = null;
    setIsLoaded(false);

    let cancelled = false;

    if (mode === "online") {
      // Configure the Ion token only if provided; an "undefined" token 401s.
      if (process.env.NEXT_PUBLIC_CESIUM_TOKEN) {
        CesiumJs.Ion.defaultAccessToken = process.env.NEXT_PUBLIC_CESIUM_TOKEN;
      }
      // Ion world imagery loads via the Ion REST endpoint (api.cesium.com). That
      // request can fail for reasons navigator.onLine cannot see: an unset/bad
      // token, or a CSP `connect-src 'self'` block in a hardened/enclave build.
      // Key the offline fallback on the imagery load actually failing, so the
      // globe degrades to the bundled Natural Earth II imagery instead of
      // rendering blank.
      const worldImagery = CesiumJs.createWorldImageryAsync();
      worldImagery.catch(() => {
        if (!cancelled) setMode("offline");
      });
      const viewer = new CesiumJs.Viewer(cesiumContainerRef.current, {
        baseLayer: CesiumJs.ImageryLayer.fromProviderAsync(worldImagery, {}),
        terrain: CesiumJs.Terrain.fromWorldTerrain(),
        ...HIDDEN_WIDGETS,
      });
      cesiumViewer.current = viewer;

      // OSM Buildings (Ion asset). Non-blocking: failure must not hide the globe
      // or the satellites.
      CesiumJs.createOsmBuildingsAsync()
        .then((osmBuildings) => {
          if (cancelled || cesiumViewer.current === null) return;
          const primitive = viewer.scene.primitives.add(osmBuildings);
          addedScenePrimitives.current.push(primitive);
        })
        .catch(() => {
          /* Ion unavailable (no token / offline) — globe still renders. */
        });
    } else {
      // Offline: bundled Natural Earth II imagery + default ellipsoid, no Ion.
      const viewer = new CesiumJs.Viewer(cesiumContainerRef.current, {
        baseLayer: CesiumJs.ImageryLayer.fromProviderAsync(
          CesiumJs.TileMapServiceImageryProvider.fromUrl(
            CesiumJs.buildModuleUrl("Assets/Textures/NaturalEarthII")
          ),
          {}
        ),
        baseLayerPicker: false,
        ...HIDDEN_WIDGETS,
      });
      cesiumViewer.current = viewer;
    }

    cesiumViewer.current.clock.clockStep =
      CesiumJs.ClockStep.SYSTEM_CLOCK_MULTIPLIER;

    // Add any provided positions as simple static point entities.
    positions.forEach((p) => {
      cesiumViewer.current?.entities.add({
        position: CesiumJs.Cartesian3.fromDegrees(p.lng, p.lat, p.height ?? 0),
        point: {
          pixelSize: 10,
          color: CesiumJs.Color.YELLOW,
          outlineColor: CesiumJs.Color.BLACK,
          outlineWidth: 1,
        },
      });
    });

    setIsLoaded(true);

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, CesiumJs]);

  // Render the full catalog as a single GPU-batched PointPrimitiveCollection
  // (dev-plan §4.3 — Entity-per-object does not scale to 10k+). Each point's
  // position is re-propagated on a throttled clock tick; selection is via
  // scene picking. Keyed on `mode` so it re-runs after every viewer rebuild.
  React.useEffect(() => {
    if (!isLoaded || !cesiumViewer.current) return;

    const viewer = cesiumViewer.current;
    const Cesium = CesiumJs;

    const points = new Cesium.PointPrimitiveCollection();
    viewer.scene.primitives.add(points);
    pointsRef.current = points;

    const satsById = new Map<string, RenderedSat>();
    satsByIdRef.current = satsById;
    // Index-aligned arrays for the Web Worker: it returns positions in this
    // same order so the main thread can update primitives by index.
    const ordered: PointPrimitive[] = [];
    const workerInputs: { line1: string; line2: string }[] = [];

    const now = new Date();

    (tleEntries ?? []).forEach((entry, index) => {
      const { TLE_LINE1: line1, TLE_LINE2: line2 } = entry;
      if (!line1 || !line2) return;

      const satrec = twoline2satrec(line1, line2);
      const id = entry.OBJECT_ID ?? entry.OBJECT_NAME ?? `sat-${index}`;
      const geo = geodeticAt(satrec, now);
      if (geo === null) return;

      const primitive = points.add({
        id,
        position: Cesium.Cartesian3.fromDegrees(geo.lon, geo.lat, geo.altM),
        pixelSize: POINT_SIZE,
        color: Cesium.Color.WHITE,
        outlineColor: Cesium.Color.BLACK,
        outlineWidth: 1,
      });

      const name = entry.OBJECT_NAME ?? id;
      satsById.set(id, {
        id,
        name,
        satrec,
        primitive,
        countryCode: entry.COUNTRY_CODE ?? null,
        constellation: classifyConstellation(name),
      });
      ordered.push(primitive);
      workerInputs.push({ line1, line2 });
    });

    // Drive the clock by real time: 1 second UTC = 1 second in the scene.
    viewer.clock.currentTime = Cesium.JulianDate.fromDate(now);
    viewer.clock.multiplier = 1;
    viewer.clock.clockStep = Cesium.ClockStep.SYSTEM_CLOCK_MULTIPLIER;
    viewer.clock.shouldAnimate = true;

    // Offload re-propagation to a Web Worker so the main thread stays
    // responsive at catalog scale (dev-plan Stage 3, keeptrack pattern). The
    // worker returns positions in `ordered` index order; the main thread only
    // writes them to the GPU points. Falls back to main-thread propagation if
    // Workers are unavailable.
    let worker: Worker | null = null;
    try {
      worker = new Worker(
        new URL("../workers/propagation.worker.ts", import.meta.url)
      );
      worker.postMessage({ type: "init", sats: workerInputs });
      worker.onmessage = (e: MessageEvent) => {
        const data = e.data as {
          type: string;
          lon: Float64Array;
          lat: Float64Array;
          alt: Float64Array;
        };
        if (data.type !== "positions" || viewer.isDestroyed()) return;
        const { lon, lat, alt } = data;
        for (let i = 0; i < ordered.length; i++) {
          if (Number.isNaN(lon[i])) continue;
          ordered[i].position = Cesium.Cartesian3.fromDegrees(
            lon[i],
            lat[i],
            alt[i]
          );
        }
      };
    } catch {
      worker = null;
    }

    // Throttled cadence (POSITION_UPDATE_SEC of sim time): ask the worker for
    // fresh positions, or compute on the main thread if there's no worker.
    let lastUpdate = now;
    const onTick = viewer.clock.onTick.addEventListener((clock) => {
      const date = Cesium.JulianDate.toDate(clock.currentTime);
      if (Math.abs(date.getTime() - lastUpdate.getTime()) < POSITION_UPDATE_SEC * 1000) {
        return;
      }
      lastUpdate = date;
      if (worker) {
        worker.postMessage({ type: "propagate", timeMs: date.getTime() });
        return;
      }
      satsById.forEach((sat) => {
        const geo = geodeticAt(sat.satrec, date);
        if (geo === null) return;
        sat.primitive.position = Cesium.Cartesian3.fromDegrees(
          geo.lon,
          geo.lat,
          geo.altM
        );
      });
    });

    // Left-click selects the object under the cursor (our points carry a string
    // id; Entities/other primitives are ignored).
    const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
    pickHandlerRef.current = handler;
    handler.setInputAction(
      (movement: ScreenSpaceEventHandler.PositionedEvent) => {
        const picked = viewer.scene.pick(movement.position) as
          | { id?: unknown }
          | undefined;
        const pickedId = picked?.id;
        if (typeof pickedId === "string" && satsById.has(pickedId)) {
          setSelectedId(pickedId);
        } else {
          setSelectedId(null);
        }
      },
      Cesium.ScreenSpaceEventType.LEFT_CLICK
    );

    return () => {
      onTick();
      if (worker) {
        worker.onmessage = null;
        worker.terminate();
      }
      if (!handler.isDestroyed()) handler.destroy();
      pickHandlerRef.current = null;
      if (!viewer.isDestroyed()) viewer.scene.primitives.remove(points);
      pointsRef.current = null;
      satsByIdRef.current = new Map();
    };
  }, [isLoaded, CesiumJs, tleEntries, mode, setSelectedId]);

  // Style every point from the current view state: selection (yellow) >
  // watchlist (orange) > country/constellation filter match (cyan) > dimmed
  // (filter active, no match) > default (white). One O(N) pass, only on a
  // selection/filter/watchlist change — not per frame.
  React.useEffect(() => {
    if (!isLoaded || !cesiumViewer.current || cesiumViewer.current.isDestroyed())
      return;

    const Cesium = CesiumJs;
    const watchSet = new Set(watchlist);
    const filterActive = Boolean(countryFilter || constellationFilter);

    satsByIdRef.current.forEach((sat) => {
      const countryOk = !countryFilter || sat.countryCode === countryFilter;
      const constOk =
        !constellationFilter || sat.constellation === constellationFilter;
      const matches = countryOk && constOk;

      let color = Cesium.Color.WHITE;
      let size = POINT_SIZE;
      if (filterActive && matches) {
        color = Cesium.Color.CYAN;
        size = MATCH_POINT_SIZE;
      } else if (filterActive) {
        color = Cesium.Color.GRAY.withAlpha(0.25);
        size = 2;
      }
      if (watchSet.has(sat.id)) {
        color = Cesium.Color.ORANGE;
        size = WATCHED_POINT_SIZE;
      }
      if (sat.id === selectedId) {
        color = Cesium.Color.YELLOW;
        size = SELECTED_POINT_SIZE;
      }
      sat.primitive.color = color;
      sat.primitive.pixelSize = size;
    });
  }, [
    selectedId,
    countryFilter,
    constellationFilter,
    watchlist,
    isLoaded,
    CesiumJs,
    tleEntries,
    mode,
  ]);

  // Draw the selected object's orbit/ground track as the single time-dynamic
  // Entity reserved for the selected handful (dev-plan §4.3). Colour of the
  // point itself is handled by the styling effect above.
  React.useEffect(() => {
    if (!isLoaded || !cesiumViewer.current) return;

    const viewer = cesiumViewer.current;
    const Cesium = CesiumJs;

    if (selectedOrbitRef.current && !viewer.isDestroyed()) {
      viewer.entities.remove(selectedOrbitRef.current);
      selectedOrbitRef.current = null;
    }

    if (selectedId === null) return;
    const sat = satsByIdRef.current.get(selectedId);
    if (!sat) return;

    // Sample one orbit around "now" for the path line.
    const property = new Cesium.SampledPositionProperty(
      Cesium.ReferenceFrame.FIXED
    );
    const center = Cesium.JulianDate.toDate(viewer.clock.currentTime).getTime();
    for (
      let t = center - ORBIT_WINDOW_SEC * 1000;
      t <= center + ORBIT_WINDOW_SEC * 1000;
      t += ORBIT_SAMPLE_STEP_SEC * 1000
    ) {
      const date = new Date(t);
      const geo = geodeticAt(sat.satrec, date);
      if (geo === null) continue;
      property.addSample(
        Cesium.JulianDate.fromDate(date),
        Cesium.Cartesian3.fromDegrees(geo.lon, geo.lat, geo.altM)
      );
    }

    selectedOrbitRef.current = viewer.entities.add({
      name: sat.name,
      position: property,
      path: {
        resolution: ORBIT_SAMPLE_STEP_SEC,
        width: 2,
        leadTime: ORBIT_PERIOD_SEC,
        trailTime: ORBIT_PERIOD_SEC,
        material: Cesium.Color.YELLOW.withAlpha(0.6),
      },
    });

    return () => {
      if (selectedOrbitRef.current && !viewer.isDestroyed()) {
        viewer.entities.remove(selectedOrbitRef.current);
        selectedOrbitRef.current = null;
      }
    };
  }, [selectedId, isLoaded, CesiumJs, tleEntries, mode]);

  // Draw the active sensor's site marker + nominal coverage ring (#9c).
  React.useEffect(() => {
    if (!isLoaded || !cesiumViewer.current) return;
    const viewer = cesiumViewer.current;
    const Cesium = CesiumJs;

    if (sensorEntityRef.current && !viewer.isDestroyed()) {
      viewer.entities.remove(sensorEntityRef.current);
      sensorEntityRef.current = null;
    }
    if (!activeSensor) return;

    sensorEntityRef.current = viewer.entities.add({
      name: activeSensor.name,
      position: Cesium.Cartesian3.fromDegrees(
        activeSensor.lonDeg,
        activeSensor.latDeg,
        0
      ),
      point: {
        pixelSize: 10,
        color: Cesium.Color.LIME,
        outlineColor: Cesium.Color.BLACK,
        outlineWidth: 1,
      },
      label: {
        text: activeSensor.name,
        font: "12px system-ui, sans-serif",
        fillColor: Cesium.Color.LIME,
        pixelOffset: new Cesium.Cartesian2(0, -16),
        style: Cesium.LabelStyle.FILL,
      },
      ellipse: {
        semiMajorAxis: activeSensor.rangeKm * 1000,
        semiMinorAxis: activeSensor.rangeKm * 1000,
        material: Cesium.Color.LIME.withAlpha(0.1),
        outline: true,
        outlineColor: Cesium.Color.LIME.withAlpha(0.5),
      },
    });

    return () => {
      if (sensorEntityRef.current && !viewer.isDestroyed()) {
        viewer.entities.remove(sensorEntityRef.current);
        sensorEntityRef.current = null;
      }
    };
  }, [activeSensor, isLoaded, CesiumJs, mode]);

  // Subscribe to the engine's authoritative latest-state stream (SSE via the
  // BFF). Each server snapshot snaps the matching points to the engine's
  // propagated position (dev-plan §4.2 — engine is authoritative); the worker
  // interpolates between snapshots. EventSource auto-reconnects.
  React.useEffect(() => {
    if (!isLoaded || !cesiumViewer.current) return;
    if (typeof window === "undefined" || typeof EventSource === "undefined")
      return;

    const viewer = cesiumViewer.current;
    const Cesium = CesiumJs;
    const es = new EventSource("/api/state/stream");

    es.addEventListener("state", (ev) => {
      if (viewer.isDestroyed()) return;
      try {
        const state = JSON.parse((ev as MessageEvent).data) as {
          objects?: Array<{
            object_id?: string;
            lat_deg: number;
            lon_deg: number;
            alt_km: number;
          }>;
        };
        for (const o of state.objects ?? []) {
          if (!o.object_id) continue;
          const sat = satsByIdRef.current.get(o.object_id);
          if (!sat) continue;
          sat.primitive.position = Cesium.Cartesian3.fromDegrees(
            o.lon_deg,
            o.lat_deg,
            o.alt_km * 1000
          );
        }
      } catch {
        /* ignore malformed snapshot */
      }
    });

    return () => es.close();
  }, [isLoaded, mode, tleEntries, CesiumJs]);

  return (
    <div style={{ position: "relative" }}>
      <button
        type="button"
        onClick={() =>
          setMode((m) => (m === "offline" ? "online" : "offline"))
        }
        style={{
          // Top-right, below the 56px fixed header. The left edge is owned by
          // the control rail (search/filters), so anchoring here keeps the
          // toggle from being hidden under the catalog search panel.
          position: "absolute",
          top: 64,
          right: 12,
          zIndex: 30,
          padding: "6px 12px",
          borderRadius: 6,
          border: "1px solid rgba(255,255,255,0.4)",
          background: "rgba(0,0,0,0.6)",
          color: "#fff",
          fontSize: 13,
          cursor: "pointer",
        }}
        title={
          mode === "offline"
            ? "Currently offline (no Ion). Switch to Ion world imagery + terrain (needs token + internet)."
            : "Currently online (Cesium Ion). Switch to bundled offline imagery."
        }
      >
        Globe: {mode === "offline" ? "Offline" : "Online (Ion)"} — switch to{" "}
        {mode === "offline" ? "Online" : "Offline"}
      </button>
      <div
        ref={cesiumContainerRef}
        id="cesium-container"
        style={{ height: "calc(100vh - 56px)", width: "100vw" }}
      />
    </div>
  );
};

export default CesiumComponent;
