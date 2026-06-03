"use client";

import React from "react";
import type { CesiumType } from "../types/cesium";
import { Cesium3DTileset, type Entity, type Viewer } from "cesium";
import type { Position } from "../types/position";
import type { TleObject } from "../utils/sgp4FromTle";
import { runOneSgp4ToLatLonAlt } from "../utils/sgp4FromTle";
//NOTE: This is required to get the stylings for default Cesium UI and controls
import "cesium/Build/Cesium/Widgets/widgets.css";

//NOTE: This is required for cpx/Next 16
if (typeof window !== "undefined") {
  (window as any).CESIUM_BASE_URL = "/cesium";
}

/** One orbit period in seconds (LEO ~90 min). Sample 1 step per second. */
const ORBIT_PERIOD_SEC = 90 * 60;
const ORBIT_WINDOW_ORBITS = 3;

/**
 * Globe data source:
 * - "offline": Cesium's bundled Natural Earth II imagery (copied into
 *   /cesium/Assets) + the default ellipsoid. No Cesium Ion, no network — works
 *   in an air-gapped enclave and requires no token.
 * - "online": Cesium Ion world imagery + world terrain + OSM Buildings. Requires
 *   NEXT_PUBLIC_CESIUM_TOKEN and internet access.
 */
type GlobeMode = "offline" | "online";

export const CesiumComponent: React.FunctionComponent<{
  CesiumJs: CesiumType;
  positions: Position[];
  tleEntries?: TleObject[];
}> = ({ CesiumJs, positions, tleEntries }) => {
  const cesiumViewer = React.useRef<Viewer | null>(null);
  const cesiumContainerRef = React.useRef<HTMLDivElement>(null);
  const addedScenePrimitives = React.useRef<Cesium3DTileset[]>([]);
  const orbitEntitiesRef = React.useRef<Entity[]>([]);
  const [isLoaded, setIsLoaded] = React.useState(false);
  const [mode, setMode] = React.useState<GlobeMode>("offline");

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
    orbitEntitiesRef.current = [];
    setIsLoaded(false);

    let cancelled = false;

    if (mode === "online") {
      // Configure the Ion token only if provided; an "undefined" token 401s.
      if (process.env.NEXT_PUBLIC_CESIUM_TOKEN) {
        CesiumJs.Ion.defaultAccessToken = process.env.NEXT_PUBLIC_CESIUM_TOKEN;
      }
      const viewer = new CesiumJs.Viewer(cesiumContainerRef.current, {
        terrain: CesiumJs.Terrain.fromWorldTerrain(),
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
        geocoder: false,
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

  // When tleEntries are provided and the viewer is ready: sample each orbit at
  // 10-second steps and add one moving entity per TLE (SampledPositionProperty)
  // so they animate in real time (1 s UTC = 1 s in scene). Keyed on `mode` so it
  // re-runs after every viewer rebuild: a mode switch calls setIsLoaded(false)
  // then setIsLoaded(true) in the same synchronous pass, which React batches to a
  // no-op (true -> true), so `isLoaded` alone never re-triggers this effect.
  React.useEffect(() => {
    if (!isLoaded || !cesiumViewer.current) {
      return;
    }

    const viewer = cesiumViewer.current;
    const Cesium = CesiumJs;

    // Remove previous orbit entities
    orbitEntitiesRef.current.forEach((entity) => {
      if (!viewer.isDestroyed()) viewer.entities.remove(entity);
    });
    orbitEntitiesRef.current = [];

    if (!tleEntries || tleEntries.length === 0) {
      return;
    }

    const now = new Date();
    const startTime = now.getTime();
    const endTime = startTime + ORBIT_WINDOW_ORBITS * ORBIT_PERIOD_SEC * 1000;

    for (const entry of tleEntries) {
      const { TLE_LINE1: line1, TLE_LINE2: line2, OBJECT_NAME: name } = entry;
      if (!line1 || !line2) continue;

      const property = new Cesium.SampledPositionProperty(
        Cesium.ReferenceFrame.FIXED
      );

      for (let t = startTime; t <= endTime; t += 10000) {
        const date = new Date(t);
        const result = runOneSgp4ToLatLonAlt(line1, line2, date);
        if (!result) continue;
        const jd = Cesium.JulianDate.fromDate(date);
        const cartesian = Cesium.Cartesian3.fromDegrees(
          result.lng,
          result.lat,
          result.height * 1000
        );
        property.addSample(jd, cartesian);
      }

      const entity = viewer.entities.add({
        name: name ?? undefined,
        availability: new Cesium.TimeIntervalCollection([
          new Cesium.TimeInterval({
            start: Cesium.JulianDate.fromDate(new Date(startTime)),
            stop: Cesium.JulianDate.fromDate(new Date(endTime)),
          }),
        ]),
        position: property,
        point: {
          pixelSize: 4,
          color: Cesium.Color.WHITE,
          outlineColor: Cesium.Color.BLACK,
        },
      });
      orbitEntitiesRef.current.push(entity);
    }

    // Drive clock by real time: 1 second UTC = 1 second in the scene
    viewer.clock.startTime = Cesium.JulianDate.fromDate(new Date(startTime));
    viewer.clock.stopTime = Cesium.JulianDate.fromDate(new Date(endTime));
    viewer.clock.currentTime = Cesium.JulianDate.fromDate(now);
    viewer.clock.multiplier = 1;
    viewer.clock.clockStep = Cesium.ClockStep.SYSTEM_CLOCK_MULTIPLIER;
    viewer.clock.shouldAnimate = true;

    return () => {
      orbitEntitiesRef.current.forEach((entity) => {
        if (!viewer.isDestroyed()) viewer.entities.remove(entity);
      });
      orbitEntitiesRef.current = [];
    };
  }, [isLoaded, CesiumJs, tleEntries, mode]);

  return (
    <div style={{ position: "relative" }}>
      <button
        type="button"
        onClick={() =>
          setMode((m) => (m === "offline" ? "online" : "offline"))
        }
        style={{
          position: "absolute",
          top: 8,
          left: 8,
          zIndex: 10,
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
