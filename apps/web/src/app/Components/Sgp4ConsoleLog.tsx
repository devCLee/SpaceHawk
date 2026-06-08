"use client";

import { useEffect } from "react";
import { runOneSgp4Calculation } from "../utils/sgp4FromTle";

// First object's TLE is passed in from the server page so the bundled catalog
// (now ~15k objects / several MB) is NOT imported into the client bundle just to
// log one propagation — only these three strings cross to the client.
export function Sgp4ConsoleLog({
  line1,
  line2,
  name,
}: {
  line1?: string;
  line2?: string;
  name?: string;
}) {
  useEffect(() => {
    if (line1 && line2) {
      console.log("Running SGP4 for first object:", name ?? "(unnamed)");
      runOneSgp4Calculation(line1, line2);
    }
  }, [line1, line2, name]);
  return null;
}
