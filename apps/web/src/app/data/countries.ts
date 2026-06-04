// Placeholder country-code → display-name map (#9d). Space-Track / CCSDS use
// short owner codes (US, PRC, CIS, …). This is a curated subset for the MVP;
// unknown codes fall back to the raw code. Replace with an authoritative
// owner/operator dataset before operational use (dev-plan Stage 3 Dependencies).

export const COUNTRY_NAMES: Record<string, string> = {
  US: "United States",
  PRC: "China",
  CIS: "Russia / CIS",
  ROK: "South Korea",
  PRK: "North Korea",
  JPN: "Japan",
  IND: "India",
  FR: "France",
  UK: "United Kingdom",
  ESA: "ESA",
  GER: "Germany",
  ITA: "Italy",
  CA: "Canada",
  ISRA: "Israel",
  IRAN: "Iran",
  GLOB: "Global / commercial",
};

export function countryName(code: string | null | undefined): string {
  if (!code) return "Unknown";
  return COUNTRY_NAMES[code] ?? code;
}
