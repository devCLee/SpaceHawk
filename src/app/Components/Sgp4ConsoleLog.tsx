"use client";

import { useEffect } from "react";
import { runOneSgp4Calculation } from "../utils/sgp4FromTle";
import mainData from "../../data/main.json";

export function Sgp4ConsoleLog() {
  useEffect(() => {
    const first = mainData[0] as { TLE_LINE1: string; TLE_LINE2: string; OBJECT_NAME?: string };
    if (first?.TLE_LINE1 && first?.TLE_LINE2) {
      console.log("Running SGP4 for first object:", first.OBJECT_NAME ?? first);
      runOneSgp4Calculation(first.TLE_LINE1, first.TLE_LINE2);
    }
  }, []);
  return null;
}
