"use client";

import React from "react";
import type { CesiumType } from "../types/cesium";
import { Cesium3DTileset, type Entity, type Viewer } from "cesium";
import type { Position } from "../types/position";
import type { TleObject } from "../utils/sgp4FromTle";
import { runOneSgp4ToLatLonAlt } from "../utils/sgp4FromTle";
import { dateToJulianDate } from "../example_utils/date";
//NOTE: This is required to get the stylings for default Cesium UI and controls
import "cesium/Build/Cesium/Widgets/widgets.css";

//NOTE: This is required for cpx/Next 16
if (typeof window !== "undefined") {
  (window as any).CESIUM_BASE_URL = "/cesium";
}

/** One orbit period in seconds (LEO ~90 min). Sample 1 step per second. */
const ORBIT_PERIOD_SEC = 90 * 60;
const ORBIT_WINDOW_ORBITS = 3;

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

  const cleanUpPrimitives = React.useCallback(() => {
    //On NextJS 13.4+, React Strict Mode is on by default.
    //The block below will remove all added primitives from the scene.
    addedScenePrimitives.current.forEach((scenePrimitive) => {
      if (cesiumViewer.current !== null) {
        cesiumViewer.current.scene.primitives.remove(scenePrimitive);
      }
    });
    addedScenePrimitives.current = [];
  }, []);

  const initializeCesiumJs = React.useCallback(async () => {
    if (cesiumViewer.current !== null) {
      //Using the Sandcastle example below
      //https://sandcastle.cesium.com/?src=3D%20Tiles%20Feature%20Styling.html
      const osmBuildingsTileset = await CesiumJs.createOsmBuildingsAsync();

      //Clean up potentially already-existing primitives.
      cleanUpPrimitives();

      //Adding tile and adding to addedScenePrimitives to keep track and delete in-case of a re-render.
      const osmBuildingsTilesetPrimitive =
        cesiumViewer.current.scene.primitives.add(osmBuildingsTileset);
      addedScenePrimitives.current.push(osmBuildingsTilesetPrimitive);

      //Add any provided positions as simple point entities (static).
      positions.forEach((p) => {
        cesiumViewer.current?.entities.add({
          position: CesiumJs.Cartesian3.fromDegrees(
            p.lng,
            p.lat,
            p.height ?? 0
          ),
          point: {
            pixelSize: 10,
            color: CesiumJs.Color.YELLOW,
            outlineColor: CesiumJs.Color.BLACK,
            outlineWidth: 1,
          },
        });
      });

      setIsLoaded(true);

      // eslint-disable-next-line react-hooks/exhaustive-deps
    }
  }, [positions]);

  React.useEffect(() => {
    if (cesiumViewer.current === null && cesiumContainerRef.current) {
      //OPTIONAL: Assign access Token here
      //Guide: https://cesium.com/learn/ion/cesium-ion-access-tokens/
      CesiumJs.Ion.defaultAccessToken = `${process.env.NEXT_PUBLIC_CESIUM_TOKEN}`;

      //NOTE: Always utilize CesiumJs; do not import them from "cesium"
      cesiumViewer.current = new CesiumJs.Viewer(cesiumContainerRef.current, {
        //Using the Sandcastle example below
        //https://sandcastle.cesium.com/?src=3D%20Tiles%20Feature%20Styling.html
        terrain: CesiumJs.Terrain.fromWorldTerrain(),
      });

      //NOTE: Example of configuring a Cesium viewer
      cesiumViewer.current.clock.clockStep =
        CesiumJs.ClockStep.SYSTEM_CLOCK_MULTIPLIER;
    }

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  React.useEffect(() => {
    if (isLoaded) return;
    initializeCesiumJs();

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [positions, isLoaded]);

  // When tleEntries are provided and viewer is ready: sample each orbit at 1-second steps and add one entity per TLE with SampledPositionProperty so they move in real time (1 s UTC = 1 s in scene).
  React.useEffect(() => {
    if (!isLoaded || !cesiumViewer.current) {
      return;
    }

    const viewer = cesiumViewer.current;
    const Cesium = CesiumJs;

    // Remove previous orbit entities
    orbitEntitiesRef.current.forEach((entity) => {
      viewer.entities.remove(entity);
    });
    orbitEntitiesRef.current = [];

    if (!tleEntries || tleEntries.length === 0) {
      return;
    }

    const now = new Date();
    const startTime = now.getTime();
    const endTime =
      startTime +
      ORBIT_WINDOW_ORBITS * ORBIT_PERIOD_SEC * 1000;

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
          // outlineWidth: 1,
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
    // viewer.clock.clockRange = Cesium.ClockRange.LOOP_STOP;

    return () => {
      orbitEntitiesRef.current.forEach((entity) => {
        viewer.entities.remove(entity);
      });
      orbitEntitiesRef.current = [];
    };
  }, [isLoaded, CesiumJs, tleEntries]);

  //NOTE: Examples of typing... See above on "import type"
  const entities: Entity[] = [];
  const julianDate = dateToJulianDate(CesiumJs, new Date());

  return (
    <div
      ref={cesiumContainerRef}
      id="cesium-container"
      style={{ height: "calc(100vh - 56px)", width: "100vw" }}
    />
  );
};

export default CesiumComponent;
