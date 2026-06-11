"use client";

import React from "react";
import type { CesiumType } from "../types/cesium";
import {
  Cesium3DTileset,
  type Entity,
  type PointPrimitive,
  type PointPrimitiveCollection,
  type ProviderViewModel,
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
import { t } from "@/lib/i18n/t";
import { useCatalogView } from "../context/CatalogViewContext";
import { useSensor } from "../context/SensorContext";
import { useGlobeControls } from "../context/GlobeControlsContext";
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

/** A catalog object: GPU point + identity + its TLE. The SGP4 record is parsed
 *  lazily (the worker propagates the catalog; the main thread only needs a
 *  satrec for the selected object's orbit line or the no-worker fallback). */
interface RenderedSat {
  id: string;
  name: string;
  line1: string;
  line2: string;
  satrec: SatRec | null;
  primitive: PointPrimitive;
  countryCode: string | null;
  constellation: string | null;
}

/** Parse a sat's TLE on demand and cache it on the record. */
function ensureSatrec(sat: RenderedSat): SatRec {
  if (sat.satrec === null) {
    sat.satrec = twoline2satrec(sat.line1, sat.line2);
  }
  return sat.satrec;
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
  // True when a WebGL rendering context can't be created (GPU-less / headless /
  // remote-tunneled environment): we show a graceful message instead of letting
  // the thrown Cesium RuntimeError crash the whole dashboard.
  const [webglError, setWebglError] = React.useState(false);
  // Globe mode lives in GlobeControls so the unified Header owns the
  // online/offline switch. Default is the bundled offline globe (Natural Earth
  // II): the app ships a strict CSP (`connect-src 'self'`, Stage 5 hardening)
  // that blocks Cesium Ion, so booting Ion would emit browser CSP-violation
  // errors plus Cesium RequestErrorEvents that can't be suppressed from JS.
  // Offline imagery is same-origin and needs no network. The online branch
  // auto-falls-back to offline if Ion is unreachable (no network / blocked /
  // bad token).
  const { mode, setMode, registerViewer } = useGlobeControls();

  // On first mount, if there is no network, tell the user why they're seeing the
  // offline globe. Fires once — manual switches afterward are intentional.
  React.useEffect(() => {
    if (typeof navigator !== "undefined" && navigator.onLine === false) {
      toast.warning(t("globe.offlineToast"));
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
    const container = cesiumContainerRef.current;

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

    // Construct the Viewer resiliently. A GPU-less / headless / remote-tunneled
    // environment can expose the WebGL2 *API* (so Cesium reports "browser
    // supports WebGL") yet fail to create a rendering context — getContext()
    // returns null and Cesium throws inside the constructor, which would crash
    // the whole React tree. Try WebGL2 first, then retry forcing WebGL1 (works
    // in some constrained GPU setups), clearing any partial widget DOM the failed
    // attempt left in the container. Returns null when no context can be made.
    const buildViewer = (
      options: ConstructorParameters<typeof Viewer>[1]
    ): Viewer | null => {
      const attempts = [
        { webgl: { failIfMajorPerformanceCaveat: false } },
        { requestWebgl1: true, webgl: { failIfMajorPerformanceCaveat: false } },
      ];
      for (const contextOptions of attempts) {
        try {
          return new CesiumJs.Viewer(container, { ...options, contextOptions });
        } catch {
          while (container.firstChild) container.removeChild(container.firstChild);
        }
      }
      return null;
    };

    // Cesium defaults to 6 concurrent requests per host. Single-host imagery
    // providers (ArcGIS/ESRI, OpenStreetMap, Stadia — the BaseLayerPicker grid)
    // then stream tiles in slow 6-at-a-time waves, so the globe visibly fills in
    // patches. Raise the per-host + global caps so a globe view's tiles fetch in
    // one sweep. Idempotent — safe to set on every viewer (re)build. (Bing hides
    // this with 4 subdomains; the others have one host, so they felt much slower.)
    CesiumJs.RequestScheduler.maximumRequestsPerServer = 18;
    CesiumJs.RequestScheduler.maximumRequests = 100;

    if (mode === "online") {
      // Configure the Ion token only if provided; an "undefined" token 401s.
      if (process.env.NEXT_PUBLIC_CESIUM_TOKEN) {
        CesiumJs.Ion.defaultAccessToken = process.env.NEXT_PUBLIC_CESIUM_TOKEN;
      }
      // Ion reachability probe: if Ion world imagery can't load (no network,
      // blocked, or bad token), fall back to the offline globe instead of a
      // half-loaded picker. navigator.onLine can't see token/CSP failures, so we
      // key the fallback on the imagery request actually failing.
      CesiumJs.createWorldImageryAsync().catch(() => {
        if (!cancelled) setMode("offline");
      });

      // Curated BaseLayerPicker. We replace Cesium's default provider grid with
      // ONLY the imagery/terrain this Ion token owns AND that loads through hosts
      // already in the strict CSP — Ion (`assets.ion.cesium.com`), Bing
      // (`*.virtualearth.net`), or same-origin. This keeps the imagery-selection
      // UX with NO Stage 5 CSP regression: the default grid's ArcGIS/ESRI/OSM/
      // Stadia options hit third-party CDNs (CSP-blocked + Stadia needs a key),
      // and several Ion defaults (Sentinel-2, Blue Marble, Earth at Night, Azure)
      // 404 on this token's account. Google tiles here are Ion-proxied via
      // assets.ion.cesium.com (verified), so no third-party origins are needed.
      // Filtering Cesium's own view models (not hand-building them) reuses their
      // correct icons, tooltips, and asset-id creation functions.
      // Cesium's default view-model names contain formatting characters (e.g.
      // "Natural Earth II" uses a non-breaking space; "Open­Street­Map"
      // uses soft hyphens), so match on a normalized form, not the raw string.
      const normalize = (s: string) =>
        s.replace(/­/g, "").replace(/\s+/g, " ").trim();
      const ownedImagery = new Set([
        "Bing Maps Aerial",
        "Bing Maps Aerial with Labels",
        "Bing Maps Roads",
        "Google Maps Satellite",
        "Google Maps Satellite with Labels",
        "Google Maps Roadmap",
        "Google Maps Contour",
        "Natural Earth II",
      ]);
      // createDefault*ProviderViewModels back Cesium's default BaseLayerPicker
      // and exist at runtime, but the umbrella "cesium" type defs only mention
      // them in JSDoc — so reach them through a narrow cast.
      const {
        createDefaultImageryProviderViewModels,
        createDefaultTerrainProviderViewModels,
      } = CesiumJs as unknown as {
        createDefaultImageryProviderViewModels: () => ProviderViewModel[];
        createDefaultTerrainProviderViewModels: () => ProviderViewModel[];
      };
      const imageryProviderViewModels =
        createDefaultImageryProviderViewModels().filter((vm) =>
          ownedImagery.has(normalize(vm.name))
        );
      const ownedTerrain = new Set(["WGS84 Ellipsoid", "Cesium World Terrain"]);
      const terrainProviderViewModels =
        createDefaultTerrainProviderViewModels().filter((vm) =>
          ownedTerrain.has(normalize(vm.name))
        );

      const viewer = buildViewer({
        imageryProviderViewModels,
        selectedImageryProviderViewModel: imageryProviderViewModels.find(
          (vm) => normalize(vm.name) === "Bing Maps Aerial"
        ),
        terrainProviderViewModels,
        selectedTerrainProviderViewModel: terrainProviderViewModels.find(
          (vm) => normalize(vm.name) === "Cesium World Terrain"
        ),
        ...HIDDEN_WIDGETS,
      });
      cesiumViewer.current = viewer;

      // OSM Buildings (Ion asset). Non-blocking: failure must not hide the globe
      // or the satellites.
      if (viewer !== null) {
        CesiumJs.createOsmBuildingsAsync()
          .then((osmBuildings) => {
            if (cancelled || cesiumViewer.current === null) return;
            const primitive = viewer.scene.primitives.add(osmBuildings);
            addedScenePrimitives.current.push(primitive);
          })
          .catch(() => {
            /* Ion unavailable (no token / offline) — globe still renders. */
          });
      }
    } else {
      // Offline: bundled Natural Earth II imagery + default ellipsoid, no Ion.
      cesiumViewer.current = buildViewer({
        baseLayer: CesiumJs.ImageryLayer.fromProviderAsync(
          CesiumJs.TileMapServiceImageryProvider.fromUrl(
            CesiumJs.buildModuleUrl("Assets/Textures/NaturalEarthII")
          ),
          {}
        ),
        baseLayerPicker: false,
        ...HIDDEN_WIDGETS,
      });
    }

    // No WebGL context could be created — surface a message rather than crash,
    // and skip the rest of the setup (which dereferences the viewer).
    if (cesiumViewer.current === null) {
      setWebglError(true);
      return () => {
        cancelled = true;
        registerViewer(null);
      };
    }
    setWebglError(false);

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
    // Hand the viewer to the Header's globe-view group (scene-mode picker,
    // imagery picker). It re-applies the user's chosen scene projection so it
    // survives this mode-driven rebuild.
    registerViewer(cesiumViewer.current);

    return () => {
      cancelled = true;
      registerViewer(null);
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

    // Cheap setup pass: one GPU point per object, keeping its raw TLE — but NO
    // twoline2satrec / propagate here. Parsing + propagating the whole catalog on
    // the main thread blocked it for ~200-500ms; that work now happens in the
    // worker. Points start hidden and are revealed as positions arrive.
    (tleEntries ?? []).forEach((entry, index) => {
      const { TLE_LINE1: line1, TLE_LINE2: line2 } = entry;
      if (!line1 || !line2) return;

      const id = entry.OBJECT_ID ?? entry.OBJECT_NAME ?? `sat-${index}`;
      const primitive = points.add({
        id,
        position: Cesium.Cartesian3.ZERO,
        show: false,
        pixelSize: POINT_SIZE,
        color: Cesium.Color.WHITE,
        outlineColor: Cesium.Color.BLACK,
        outlineWidth: 1,
      });

      const name = entry.OBJECT_NAME ?? id;
      satsById.set(id, {
        id,
        name,
        line1,
        line2,
        satrec: null,
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

    // Apply a batch of worker-computed positions: snap each valid point into
    // place and reveal it (NaN = unparseable TLE — leave it hidden).
    const applyPositions = (
      lon: Float64Array,
      lat: Float64Array,
      alt: Float64Array
    ) => {
      for (let i = 0; i < ordered.length; i++) {
        if (Number.isNaN(lon[i])) continue;
        const p = ordered[i];
        p.position = Cesium.Cartesian3.fromDegrees(lon[i], lat[i], alt[i]);
        if (!p.show) p.show = true;
      }
    };

    // Offload ALL propagation — including the first frame — to a Web Worker so
    // the main thread never parses or propagates the full catalog (dev-plan
    // Stage 3, keeptrack pattern). The worker parses the TLE set once on init
    // (the main thread no longer parses it too — that was a duplicate pass), and
    // we ask for the initial positions immediately so points appear without
    // waiting for the first throttled clock tick.
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
          alt: Float64Array;
        };
        if (data.type !== "positions" || viewer.isDestroyed()) return;
        applyPositions(data.lon, data.lat, data.alt);
      };
      worker.postMessage({ type: "init", sats: workerInputs });
      worker.postMessage({ type: "propagate", timeMs: now.getTime() });
    } catch {
      worker = null;
    }

    // No Worker available (headless / unsupported): propagate on the main thread.
    // satrecs are parsed lazily here and ONLY in this fallback path — the common
    // (worker) path never parses on the main thread.
    const propagateOnMainThread = (date: Date) => {
      satsById.forEach((sat) => {
        const geo = geodeticAt(ensureSatrec(sat), date);
        if (geo === null) return;
        sat.primitive.position = Cesium.Cartesian3.fromDegrees(
          geo.lon,
          geo.lat,
          geo.altM
        );
        if (!sat.primitive.show) sat.primitive.show = true;
      });
    };
    if (!worker) propagateOnMainThread(now); // seed the first frame

    // Throttled cadence (POSITION_UPDATE_SEC of sim time): ask the worker for
    // fresh positions, or compute on the main thread if there's no worker.
    let lastUpdate = now;
    const onTick = viewer.clock.onTick.addEventListener((clock) => {
      const date = Cesium.JulianDate.toDate(clock.currentTime);
      if (
        Math.abs(date.getTime() - lastUpdate.getTime()) <
        POSITION_UPDATE_SEC * 1000
      ) {
        return;
      }
      lastUpdate = date;
      if (worker) {
        worker.postMessage({ type: "propagate", timeMs: date.getTime() });
        return;
      }
      propagateOnMainThread(date);
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
    if (
      !isLoaded ||
      !cesiumViewer.current ||
      cesiumViewer.current.isDestroyed()
    )
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
      const geo = geodeticAt(ensureSatrec(sat), date);
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

  // The globe's online/offline switch, scene-mode picker, and imagery/terrain
  // picker now live in the unified Header (driven through GlobeControls); this
  // component just renders the Cesium canvas.
  return (
    <div style={{ position: "relative" }}>
      <div
        ref={cesiumContainerRef}
        id="cesium-container"
        style={{ height: "calc(100vh - 56px)", width: "100vw" }}
      />
      {webglError && (
        <div
          role="alert"
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: 12,
            padding: 24,
            textAlign: "center",
            background: "#0b0f1a",
            color: "#e5e7eb",
          }}
        >
          <p style={{ fontWeight: 600, fontSize: 16, margin: 0 }}>
            {t("globe.webglErrorTitle")}
          </p>
          <p style={{ maxWidth: 520, fontSize: 14, opacity: 0.8, margin: 0 }}>
            {t("globe.webglErrorBody")}
          </p>
        </div>
      )}
    </div>
  );
};

export default CesiumComponent;
