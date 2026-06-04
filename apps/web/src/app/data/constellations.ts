// Placeholder constellation membership (#9e), classified by object-name pattern.
// keeptrack ships a curated membership dataset under AGPL; this name-prefix
// heuristic is an independent, permissive stand-in for the MVP. Replace with a
// curated membership table before operational use (dev-plan Stage 3 Dependencies).

export interface ConstellationDef {
  key: string;
  label: string;
  /** Matches against the upper-cased object name. */
  match: RegExp;
}

export const CONSTELLATIONS: ConstellationDef[] = [
  { key: "STARLINK", label: "Starlink", match: /^STARLINK/ },
  { key: "ONEWEB", label: "OneWeb", match: /ONEWEB/ },
  { key: "GPS", label: "GPS (NAVSTAR)", match: /(^GPS|NAVSTAR)/ },
  { key: "GLONASS", label: "GLONASS", match: /GLONASS|COSMOS 2\d{3}/ },
  { key: "GALILEO", label: "Galileo", match: /GALILEO|GSAT0/ },
  { key: "BEIDOU", label: "BeiDou", match: /BEIDOU|BDS/ },
  { key: "IRIDIUM", label: "Iridium", match: /^IRIDIUM/ },
  { key: "GLOBALSTAR", label: "Globalstar", match: /GLOBALSTAR/ },
  { key: "ORBCOMM", label: "Orbcomm", match: /ORBCOMM/ },
  { key: "PLANET", label: "Planet (Flock/SkySat)", match: /FLOCK|SKYSAT/ },
];

/** Return the constellation key for an object name, or null if none. */
export function classifyConstellation(
  name: string | null | undefined
): string | null {
  if (!name) return null;
  const upper = name.toUpperCase();
  for (const c of CONSTELLATIONS) {
    if (c.match.test(upper)) return c.key;
  }
  return null;
}
