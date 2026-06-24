"use client";

import React from "react";
// Cesium is NOT imported here — it is loaded as a prebuilt UMD <script> by
// CesiumWrapper and passed in as the `CesiumJs` prop (window.Cesium). Webpack
// bundling cesium crashed the prod renderer while evaluating the chunk, so this
// module stays cesium-free at runtime; only TYPE imports from "cesium" remain
// (erased at build time, so they pull in no cesium code).
import type { CesiumType } from "../types/cesium";
import {
  type Cesium3DTileset,
  type Cartesian3,
  type Color,
  type Entity,
  type JulianDate,
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
  eciToEcf,
  degreesLat,
  degreesLong,
  type SatRec,
} from "satellite.js";
import type { Position } from "../types/position";
import {
  regimeFromTle,
  type TleObject,
  type OrbitRegime,
} from "../utils/sgp4FromTle";
import { useSelectedSatellite } from "../context/SelectedSatelliteContext";
import { t } from "@/lib/i18n/t";
import { useCatalogView } from "../context/CatalogViewContext";
import { useSensor } from "../context/SensorContext";
import { useSensorVolume } from "../context/SensorVolumeContext";
import { useGlobeControls } from "../context/GlobeControlsContext";
import {
  sensorVolumeGeometry,
  type SensorVolumeGeometry,
} from "../utils/sensorVolume";
import { classifyConstellation } from "../data/constellations";
import {
  classifyObjectType,
  categoryColor,
  categoriesFor,
  CATEGORY_FALLBACK_COLOR,
  riskColor,
  RISK_ORDER,
  type ObjectCategory,
  type DebrisRiskLevel,
} from "../data/visualization";
import { useDebrisLayer } from "../context/DebrisLayerContext";
import type { Debris } from "@/lib/orbital-engine";
import {
  SatelliteHoverCard,
  type SatelliteHoverInfo,
} from "./SatelliteHoverCard";
import { toast } from "sonner";

//NOTE: This is required for cpx/Next 16
if (typeof window !== "undefined") {
  (window as any).CESIUM_BASE_URL = "/cesium";
}

/** Fallback orbit period (s) when mean motion is unavailable — LEO ~90 min. */
const ORBIT_PERIOD_FALLBACK_SEC = 90 * 60;
/** ECI samples drawn across one orbital period for the selected object's orbit
 *  line; the line is rendered as a closed inertial ring (see the orbit effect),
 *  so this controls how round the ellipse looks. */
const ORBIT_SAMPLES_PER_PERIOD = 256;
/** How often (sim seconds) the full catalog's point positions are re-propagated. */
const POSITION_UPDATE_SEC = 1;

/** Region-of-interest box (Korean theatre) — mirrors the engine's ROI gate
 *  (orbital_engine config roi_lat/lon_*): an object inside this lat/lon box trips
 *  the region-entry alert. Drawn as an optional overlay rectangle on the globe. */
const ROI_BOUNDS = { west: 124.0, south: 33.0, east: 132.0, north: 43.0 } as const;

const POINT_SIZE = 3;
const SELECTED_POINT_SIZE = 10;
const WATCHED_POINT_SIZE = 6;
const MATCH_POINT_SIZE = 4;

// Debris layer: crisp points sized up a little by risk so Critical fragments
// stand out. (The risk-density heatmap is a separate 2D overlay — DebrisHeatmap2D.)
const DEBRIS_RISK_SIZE: Record<DebrisRiskLevel, number> = {
  Critical: 6,
  High: 5,
  Medium: 4,
  Low: 3,
};

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
  /** Object class + orbit regime — the two colour-by axes (#viz). Derived once
   *  at build time (regime is a cheap TLE-column read, no SGP4 parse). */
  category: ObjectCategory;
  regime: OrbitRegime | null;
  /** True once a valid propagated position has been applied to the primitive.
   *  Shown = hasPosition && visible: the position pipeline reveals points as
   *  they are computed, the styling pass hides whole categories on demand —
   *  this flag keeps the two writers of `primitive.show` from fighting. */
  hasPosition: boolean;
  /** False when this object's category is toggled off in the viz panel. */
  visible: boolean;
}

/** Parse a sat's TLE on demand and cache it on the record. */
function ensureSatrec(sat: RenderedSat): SatRec {
  if (sat.satrec === null) {
    sat.satrec = twoline2satrec(sat.line1, sat.line2);
  }
  return sat.satrec;
}

/** A debris object: GPU point + identity + its TLE + collision-risk level (the
 *  colour axis for the debris layer). Selection ids are prefixed `debris:` so the
 *  pick handler and the info panels can tell debris from catalog objects. */
interface RenderedDebris {
  id: string;
  name: string;
  line1: string;
  line2: string;
  satrec: SatRec | null;
  primitive: PointPrimitive;
  riskLevel: DebrisRiskLevel;
  hasPosition: boolean;
  visible: boolean;
}

/** Parse a debris object's TLE on demand and cache it on the record. */
function ensureDebrisSatrec(d: RenderedDebris): SatRec {
  if (d.satrec === null) {
    d.satrec = twoline2satrec(d.line1, d.line2);
  }
  return d.satrec;
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
  debrisEntries?: Debris[];
}> = ({ CesiumJs, positions, tleEntries, debrisEntries }) => {
  const cesiumViewer = React.useRef<Viewer | null>(null);
  const cesiumContainerRef = React.useRef<HTMLDivElement>(null);
  const addedScenePrimitives = React.useRef<Cesium3DTileset[]>([]);
  const pointsRef = React.useRef<PointPrimitiveCollection | null>(null);
  const satsByIdRef = React.useRef<Map<string, RenderedSat>>(new Map());
  const debrisPointsRef = React.useRef<PointPrimitiveCollection | null>(null);
  const debrisByIdRef = React.useRef<Map<string, RenderedDebris>>(new Map());
  const pickHandlerRef = React.useRef<ScreenSpaceEventHandler | null>(null);
  // Hover read-out: the card mirrors whatever catalog point is under the cursor.
  // `hoverIdRef` dedupes the high-frequency MOUSE_MOVE so we only re-render on a
  // real change (new object, or moving while still over one), not on every pixel.
  const [hovered, setHovered] = React.useState<SatelliteHoverInfo | null>(null);
  const hoverIdRef = React.useRef<string | null>(null);
  const selectedOrbitRef = React.useRef<Entity | null>(null);
  const sensorEntityRef = React.useRef<Entity | null>(null);
  const sensorVolumeRef = React.useRef<Entity | null>(null);
  const roiEntityRef = React.useRef<Entity | null>(null);
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
  const { mode, setMode, registerViewer, roiVisible } = useGlobeControls();

  // On first mount, if there is no network, tell the user why they're seeing the
  // offline globe. Fires once — manual switches afterward are intentional.
  React.useEffect(() => {
    if (typeof navigator !== "undefined" && navigator.onLine === false) {
      toast.warning(t("globe.offlineToast"));
    }
  }, []);
  const { selectedId, setSelectedId } = useSelectedSatellite();
  const {
    countryFilter,
    constellationFilter,
    watchlist,
    colorMode,
    hiddenCategories,
    watchlistOnly,
  } = useCatalogView();
  const { activeSensor } = useSensor();
  const {
    enabled: sensorVolumeEnabled,
    halfAngleDeg: sensorHalfAngleDeg,
  } = useSensorVolume();
  const { visible: debrisVisible, hiddenRisks } = useDebrisLayer();

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
    debrisPointsRef.current = null;
    debrisByIdRef.current = new Map();
    selectedOrbitRef.current = null;
    sensorEntityRef.current = null;
    sensorVolumeRef.current = null;
    roiEntityRef.current = null;
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
    registerViewer(cesiumViewer.current, CesiumJs);

    return () => {
      cancelled = true;
      registerViewer(null);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

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
    // same order so the main thread can update the matching sat by index.
    const ordered: RenderedSat[] = [];
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
      const sat: RenderedSat = {
        id,
        name,
        line1,
        line2,
        satrec: null,
        primitive,
        countryCode: entry.COUNTRY_CODE ?? null,
        constellation: classifyConstellation(name),
        category: classifyObjectType(name, entry.OBJECT_TYPE),
        regime: regimeFromTle(line2),
        hasPosition: false,
        visible: true,
      };
      satsById.set(id, sat);
      ordered.push(sat);
      workerInputs.push({ line1, line2 });
    });

    // Drive the clock by real time: 1 second UTC = 1 second in the scene.
    viewer.clock.currentTime = Cesium.JulianDate.fromDate(now);
    viewer.clock.multiplier = 1;
    viewer.clock.clockStep = Cesium.ClockStep.SYSTEM_CLOCK_MULTIPLIER;
    viewer.clock.shouldAnimate = true;

    // Apply a batch of worker-computed positions: snap each valid point into
    // place and reveal it unless its category is toggled off (NaN = unparseable
    // TLE — leave it hidden).
    const applyPositions = (
      lon: Float64Array,
      lat: Float64Array,
      alt: Float64Array
    ) => {
      for (let i = 0; i < ordered.length; i++) {
        if (Number.isNaN(lon[i])) continue;
        const sat = ordered[i];
        sat.primitive.position = Cesium.Cartesian3.fromDegrees(
          lon[i],
          lat[i],
          alt[i]
        );
        sat.hasPosition = true;
        if (sat.primitive.show !== sat.visible) sat.primitive.show = sat.visible;
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
        sat.hasPosition = true;
        if (sat.primitive.show !== sat.visible) sat.primitive.show = sat.visible;
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
        // Points carry a string id — catalog ids select a satellite; `debris:`
        // ids (resolved via the debris layer's map) select a debris object.
        if (
          typeof pickedId === "string" &&
          (satsById.has(pickedId) || debrisByIdRef.current.has(pickedId))
        ) {
          setSelectedId(pickedId);
        } else {
          setSelectedId(null);
        }
      },
      Cesium.ScreenSpaceEventType.LEFT_CLICK
    );

    // Hover surfaces a compact info card for the catalog point under the cursor.
    // Scoped to catalog satellites (debris has no owner/flag — its own panel owns
    // it). `endPosition` is canvas-relative, which is also the hover card's
    // coordinate space (it's absolutely positioned inside the same wrapper).
    handler.setInputAction(
      (movement: ScreenSpaceEventHandler.MotionEvent) => {
        const picked = viewer.scene.pick(movement.endPosition) as
          | { id?: unknown }
          | undefined;
        const pickedId = picked?.id;
        if (typeof pickedId === "string" && satsById.has(pickedId)) {
          const sat = satsById.get(pickedId)!;
          hoverIdRef.current = pickedId;
          setHovered({
            id: sat.id,
            name: sat.name,
            countryCode: sat.countryCode,
            category: sat.category,
            regime: sat.regime,
            constellation: sat.constellation,
            x: movement.endPosition.x,
            y: movement.endPosition.y,
          });
        } else if (hoverIdRef.current !== null) {
          hoverIdRef.current = null;
          setHovered(null);
        }
      },
      Cesium.ScreenSpaceEventType.MOUSE_MOVE
    );

    return () => {
      onTick();
      hoverIdRef.current = null;
      setHovered(null);
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
  }, [isLoaded, tleEntries, mode, setSelectedId, CesiumJs]);

  // Style every point from the current view state, in one O(N) pass that only
  // runs on a colour/selection/filter/watchlist change — not per frame.
  // Base colour is the object's category under the active colour mode (orbit
  // regime or object class, #viz); overlays then take precedence:
  // selection (yellow) > watchlist (orange) > country/constellation match (cyan)
  // > dimmed (filter active, no match) > category colour. Categories toggled off
  // in the viz panel are hidden via `show` (selection still forces visible).
  React.useEffect(() => {
    if (
      !isLoaded ||
      !cesiumViewer.current ||
      cesiumViewer.current.isDestroyed()
    )
      return;

    const Cesium = CesiumJs;
    const watchSet = new Set(watchlist);
    const hiddenSet = new Set(hiddenCategories);
    const filterActive = Boolean(countryFilter || constellationFilter);

    // Parse the small (≤4) palette once into Cesium colours, not per object.
    const palette: Record<string, Color> = {};
    for (const key of categoriesFor(colorMode)) {
      palette[key] = Cesium.Color.fromCssColorString(
        categoryColor(colorMode, key)
      );
    }
    const fallbackColor = Cesium.Color.fromCssColorString(
      CATEGORY_FALLBACK_COLOR
    );

    satsByIdRef.current.forEach((sat) => {
      const catKey = colorMode === "type" ? sat.category : sat.regime;
      const isSelected = sat.id === selectedId;
      const inWatch = watchSet.has(sat.id);
      // Hide a whole category on demand, or everything outside the watchlist when
      // watchlist-only mode is on — but a selected object stays visible (it may
      // have been picked from a panel before its category/mode hid it).
      const hidden =
        !isSelected &&
        ((catKey !== null && hiddenSet.has(catKey)) ||
          (watchlistOnly && !inWatch));
      sat.visible = !hidden;

      const countryOk = !countryFilter || sat.countryCode === countryFilter;
      const constOk =
        !constellationFilter || sat.constellation === constellationFilter;
      const matches = countryOk && constOk;

      let color = (catKey && palette[catKey]) || fallbackColor;
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
      if (isSelected) {
        color = Cesium.Color.YELLOW;
        size = SELECTED_POINT_SIZE;
      }
      sat.primitive.color = color;
      sat.primitive.pixelSize = size;
      // When the dedicated debris layer is on, hide the main catalog's DEBRIS
      // points so debris shows once (risk-coloured) rather than twice; a selected
      // object always stays visible.
      const debrisDeduped =
        debrisVisible && sat.category === "DEBRIS" && !isSelected;
      sat.primitive.show = sat.hasPosition && sat.visible && !debrisDeduped;
    });
  }, [
    selectedId,
    countryFilter,
    constellationFilter,
    watchlist,
    colorMode,
    hiddenCategories,
    watchlistOnly,
    isLoaded,
    tleEntries,
    mode,
    debrisVisible,
    CesiumJs,
  ]);

  // Render the tracked-debris population as a SECOND GPU PointPrimitiveCollection
  // (independent of the catalog layer), propagated by its own Web Worker on the
  // same throttled clock tick. Built only while the layer is visible (no wasted
  // propagation when off). Points carry a `debris:`-prefixed id so the shared pick
  // handler selects them; colour/visibility come from the styling pass below.
  React.useEffect(() => {
    if (!isLoaded || !cesiumViewer.current || !debrisVisible) return;

    const viewer = cesiumViewer.current;
    const Cesium = CesiumJs;

    const points = new Cesium.PointPrimitiveCollection();
    viewer.scene.primitives.add(points);
    debrisPointsRef.current = points;

    const byId = new Map<string, RenderedDebris>();
    debrisByIdRef.current = byId;
    const ordered: RenderedDebris[] = [];
    const workerInputs: { line1: string; line2: string }[] = [];
    const now = new Date();

    (debrisEntries ?? []).forEach((d) => {
      const line1 = d.tle_line1;
      const line2 = d.tle_line2;
      if (!line1 || !line2) return;
      const id = `debris:${d.object_id}`;
      const primitive = points.add({
        id,
        position: Cesium.Cartesian3.ZERO,
        show: false,
        pixelSize: POINT_SIZE,
        color: Cesium.Color.WHITE,
        outlineColor: Cesium.Color.BLACK,
        outlineWidth: 1,
      });
      const rec: RenderedDebris = {
        id,
        name: d.object_name,
        line1,
        line2,
        satrec: null,
        primitive,
        riskLevel: (d.risk_level as DebrisRiskLevel) || "Low",
        hasPosition: false,
        visible: true,
      };
      byId.set(id, rec);
      ordered.push(rec);
      workerInputs.push({ line1, line2 });
    });

    // Snap worker-computed positions onto the index-aligned debris primitives.
    const applyPositions = (
      lon: Float64Array,
      lat: Float64Array,
      alt: Float64Array
    ) => {
      for (let i = 0; i < ordered.length; i++) {
        if (Number.isNaN(lon[i])) continue;
        const rec = ordered[i];
        rec.primitive.position = Cesium.Cartesian3.fromDegrees(
          lon[i],
          lat[i],
          alt[i]
        );
        rec.hasPosition = true;
        if (rec.primitive.show !== rec.visible) rec.primitive.show = rec.visible;
      }
    };

    // Second worker instance — same {init, propagate} contract as the catalog.
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

    // No-worker (headless) fallback: propagate the debris set on the main thread.
    const propagateOnMainThread = (date: Date) => {
      byId.forEach((rec) => {
        const geo = geodeticAt(ensureDebrisSatrec(rec), date);
        if (geo === null) return;
        rec.primitive.position = Cesium.Cartesian3.fromDegrees(
          geo.lon,
          geo.lat,
          geo.altM
        );
        rec.hasPosition = true;
        if (rec.primitive.show !== rec.visible) rec.primitive.show = rec.visible;
      });
    };
    if (!worker) propagateOnMainThread(now);

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

    return () => {
      onTick();
      if (worker) {
        worker.onmessage = null;
        worker.terminate();
      }
      if (!viewer.isDestroyed()) viewer.scene.primitives.remove(points);
      debrisPointsRef.current = null;
      debrisByIdRef.current = new Map();
    };
  }, [isLoaded, debrisEntries, mode, debrisVisible, CesiumJs]);

  // Style every debris point by collision-risk level — one O(N) pass that runs
  // only on a layer/risk-filter/selection change (not per frame). Hidden when the
  // layer is off or its risk tier is filtered out; selection forces yellow.
  React.useEffect(() => {
    if (
      !isLoaded ||
      !cesiumViewer.current ||
      cesiumViewer.current.isDestroyed()
    )
      return;

    const Cesium = CesiumJs;
    const hiddenSet = new Set(hiddenRisks);

    // Parse the 4-colour risk palette once into Cesium colours, not per object.
    const palette: Record<string, Color> = {};
    for (const level of RISK_ORDER) {
      palette[level] = Cesium.Color.fromCssColorString(riskColor(level));
    }
    const fallbackColor = Cesium.Color.fromCssColorString(
      CATEGORY_FALLBACK_COLOR
    );

    debrisByIdRef.current.forEach((rec) => {
      const isSelected = rec.id === selectedId;
      const riskHidden = hiddenSet.has(rec.riskLevel);
      rec.visible = debrisVisible && (isSelected || !riskHidden);

      let color = palette[rec.riskLevel] ?? fallbackColor;
      let size = DEBRIS_RISK_SIZE[rec.riskLevel];
      if (isSelected) {
        color = Cesium.Color.YELLOW;
        size = SELECTED_POINT_SIZE;
      }
      rec.primitive.color = color;
      rec.primitive.pixelSize = size;
      rec.primitive.show = rec.hasPosition && rec.visible;
    });
  }, [
    debrisVisible,
    hiddenRisks,
    selectedId,
    isLoaded,
    debrisEntries,
    mode,
    CesiumJs,
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

    // The orbit must be drawn in the INERTIAL frame: an orbit is a closed
    // ellipse fixed in inertial space, while the same positions in the
    // Earth-fixed frame trace a ground track — an open sinusoid that precesses
    // westward every revolution and never closes (the previous "two ends" bug).
    // A Cesium `path` graphic also re-derives that ground track because it plots
    // position-at-time in the rotating world, so we instead build a static
    // closed polyline.
    //
    // satrec.no is mean motion in rad/min, so period(s) = 2π/no × 60. We sample
    // ECI (TEME) positions across exactly one period — the loop closes back on
    // itself — then render them with a CallbackProperty that rotates the fixed
    // inertial ring into the Earth-fixed frame by GMST at the current clock
    // time, so the ring sits correctly on the globe and turns with it.
    const satrec = ensureSatrec(sat);
    const periodSec =
      satrec.no > 0
        ? ((2 * Math.PI) / satrec.no) * 60
        : ORBIT_PERIOD_FALLBACK_SEC;
    const center = Cesium.JulianDate.toDate(viewer.clock.currentTime).getTime();

    const eciSamples: { x: number; y: number; z: number }[] = [];
    for (let i = 0; i <= ORBIT_SAMPLES_PER_PERIOD; i++) {
      const date = new Date(
        center + (i / ORBIT_SAMPLES_PER_PERIOD) * periodSec * 1000
      );
      const pv = propagate(satrec, date);
      if (pv === null || pv.position == null) continue;
      eciSamples.push({ x: pv.position.x, y: pv.position.y, z: pv.position.z });
    }
    // Close the ring exactly, in case secular drift left a small end gap.
    if (eciSamples.length > 1) eciSamples.push(eciSamples[0]);

    selectedOrbitRef.current = viewer.entities.add({
      name: sat.name,
      polyline: {
        positions: new Cesium.CallbackProperty((time) => {
          const gmst = gstime(
            Cesium.JulianDate.toDate(time ?? viewer.clock.currentTime)
          );
          return eciSamples.map((p) => {
            const ecf = eciToEcf(p, gmst); // km
            return new Cesium.Cartesian3(
              ecf.x * 1000,
              ecf.y * 1000,
              ecf.z * 1000
            );
          });
        }, false),
        // Straight 3-D segments between samples; without this Cesium draws
        // geodesics clamped to the ellipsoid surface, flattening the orbit.
        arcType: Cesium.ArcType.NONE,
        width: 2,
        material: Cesium.Color.YELLOW.withAlpha(0.6),
      },
    });

    return () => {
      if (selectedOrbitRef.current && !viewer.isDestroyed()) {
        viewer.entities.remove(selectedOrbitRef.current);
        selectedOrbitRef.current = null;
      }
    };
  }, [selectedId, isLoaded, tleEntries, mode, CesiumJs]);

  // Draw the SELECTED object's sensor-coverage volume — the area its onboard
  // sensor can observe — as a translucent nadir cone (apex at the satellite,
  // base on the footprint) plus the ground footprint disk. One time-dynamic
  // Entity (like the orbit line) so it tracks the satellite as the clock runs;
  // toggled per-selection from the info panel (SensorVolumeContext). Applies to
  // ALL orbit regimes: the geometry (sensorVolume.ts) is altitude-parametric and
  // clamps the half-angle to the horizon, so GEO/MEO render a correct, bounded
  // field-of-regard just as LEO does.
  React.useEffect(() => {
    if (!isLoaded || !cesiumViewer.current) return;

    const viewer = cesiumViewer.current;
    const Cesium = CesiumJs;

    if (sensorVolumeRef.current && !viewer.isDestroyed()) {
      viewer.entities.remove(sensorVolumeRef.current);
      sensorVolumeRef.current = null;
    }

    if (!sensorVolumeEnabled || selectedId === null) return;
    const sat = satsByIdRef.current.get(selectedId);
    if (!sat) return;

    const satrec = ensureSatrec(sat);

    // Recompute the sat's geodetic position + footprint geometry once per clock
    // time — each frame queries several CallbackProperties with the same `time`,
    // so memoise on the millisecond to run SGP4 + the trig a single time.
    let cachedMs = Number.NaN;
    let cached: { lon: number; lat: number; geom: SensorVolumeGeometry } | null =
      null;
    const computeAt = (
      time?: JulianDate
    ): { lon: number; lat: number; geom: SensorVolumeGeometry } | null => {
      if (!time) return null;
      const ms = Cesium.JulianDate.toDate(time).getTime();
      if (ms === cachedMs) return cached;
      cachedMs = ms;
      const geo = geodeticAt(satrec, new Date(ms));
      const geom =
        geo === null
          ? null
          : sensorVolumeGeometry(geo.altM / 1000, sensorHalfAngleDeg);
      cached =
        geo === null || geom === null
          ? null
          : { lon: geo.lon, lat: geo.lat, geom };
      return cached;
    };

    // Cone (cylinder with a zero top radius): the entity position is the cone
    // CENTRE on the nadir line; the apex sits at the satellite and the base
    // radius is the footprint rim's horizontal extent. Lengths/radii are metres.
    const conePosition = new Cesium.CallbackPositionProperty(
      (time?: JulianDate, result?: Cartesian3) => {
        const c = computeAt(time);
        if (c === null) return undefined;
        return Cesium.Cartesian3.fromDegrees(
          c.lon,
          c.lat,
          c.geom.coneCenterAltitudeKm * 1000,
          undefined,
          result
        );
      },
      false
    );
    const coneLength = new Cesium.CallbackProperty((time?: JulianDate) => {
      const c = computeAt(time);
      return c === null ? 0 : c.geom.coneLengthKm * 1000;
    }, false);
    const coneBottomRadius = new Cesium.CallbackProperty((time?: JulianDate) => {
      const c = computeAt(time);
      return c === null ? 0 : c.geom.coneBaseRadiusKm * 1000;
    }, false);
    // Footprint disk: drawn at sea level (height 0) centred on the sub-satellite
    // point with the geodesic coverage radius — the literal "area observed".
    const footprintRadius = new Cesium.CallbackProperty((time?: JulianDate) => {
      const c = computeAt(time);
      return c === null ? 0 : c.geom.groundRadiusKm * 1000;
    }, false);

    const sensorColor = Cesium.Color.CYAN;
    sensorVolumeRef.current = viewer.entities.add({
      name: `${sat.name} sensor volume`,
      position: conePosition,
      cylinder: {
        length: coneLength,
        topRadius: 0,
        bottomRadius: coneBottomRadius,
        material: sensorColor.withAlpha(0.12),
        outline: true,
        outlineColor: sensorColor.withAlpha(0.5),
      },
      ellipse: {
        semiMajorAxis: footprintRadius,
        semiMinorAxis: footprintRadius,
        height: 0,
        material: sensorColor.withAlpha(0.18),
        outline: true,
        outlineColor: sensorColor.withAlpha(0.7),
      },
    });

    return () => {
      if (sensorVolumeRef.current && !viewer.isDestroyed()) {
        viewer.entities.remove(sensorVolumeRef.current);
        sensorVolumeRef.current = null;
      }
    };
  }, [
    selectedId,
    isLoaded,
    tleEntries,
    mode,
    sensorVolumeEnabled,
    sensorHalfAngleDeg,
    CesiumJs,
  ]);

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
  }, [activeSensor, isLoaded, mode, CesiumJs]);

  // Optional region-of-interest overlay: the Korean-theatre lat/lon box the engine
  // screens for region entry (ROI_BOUNDS mirrors the engine's roi_* gate). Toggled
  // from the Header globe-view group via GlobeControls; drawn as a single
  // translucent rectangle. Keyed on `mode` so it re-draws after a viewer rebuild.
  React.useEffect(() => {
    if (!isLoaded || !cesiumViewer.current) return;
    const viewer = cesiumViewer.current;
    const Cesium = CesiumJs;

    if (roiEntityRef.current && !viewer.isDestroyed()) {
      viewer.entities.remove(roiEntityRef.current);
      roiEntityRef.current = null;
    }
    if (!roiVisible) return;

    const roiColor = Cesium.Color.fromCssColorString("#f43f5e");
    roiEntityRef.current = viewer.entities.add({
      name: t("globe.roi.show"),
      rectangle: {
        coordinates: Cesium.Rectangle.fromDegrees(
          ROI_BOUNDS.west,
          ROI_BOUNDS.south,
          ROI_BOUNDS.east,
          ROI_BOUNDS.north
        ),
        height: 0,
        material: roiColor.withAlpha(0.08),
        outline: true,
        outlineColor: roiColor.withAlpha(0.8),
      },
    });

    return () => {
      if (roiEntityRef.current && !viewer.isDestroyed()) {
        viewer.entities.remove(roiEntityRef.current);
        roiEntityRef.current = null;
      }
    };
  }, [roiVisible, isLoaded, mode, CesiumJs]);

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
          sat.hasPosition = true;
          if (sat.primitive.show !== sat.visible) {
            sat.primitive.show = sat.visible;
          }
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
      <SatelliteHoverCard info={hovered} />
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
