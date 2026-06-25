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

// Space-Track owner code → ISO 3166-1 alpha-2 (the code country-flag-icons keys
// its SVGs by). Covers the curated COUNTRY_NAMES set plus the common long-tail
// owners; intergovernmental/agency owners map to the EU flag, and global /
// commercial / unknown owners return null so the hover card shows no flag.
const COUNTRY_ISO: Record<string, string> = {
  US: "US",
  PRC: "CN",
  CIS: "RU",
  ROK: "KR",
  PRK: "KP",
  JPN: "JP",
  IND: "IN",
  FR: "FR",
  UK: "GB",
  GER: "DE",
  ITA: "IT",
  CA: "CA",
  ISRA: "IL",
  IRAN: "IR",
  ESA: "EU",
  EUME: "EU", // EUMETSAT
  EUTE: "EU", // EUTELSAT
  AUS: "AU",
  BRAZ: "BR",
  TWN: "TW",
  NOR: "NO",
  SWED: "SE",
  SPN: "ES",
  NETH: "NL",
  SWTZ: "CH",
  BEL: "BE",
  DEN: "DK",
  FIN: "FI",
  POL: "PL",
  POR: "PT",
  GREC: "GR",
  LUXE: "LU",
  CZCH: "CZ",
  TURK: "TR",
  UAE: "AE",
  SAUD: "SA",
  QAT: "QA",
  EGYP: "EG",
  THAI: "TH",
  INDO: "ID",
  MALA: "MY",
  SING: "SG",
  ARGN: "AR",
  CHLE: "CL",
  MEX: "MX",
  VTNM: "VN",
  KAZ: "KZ",
  UKR: "UA",
  PAKI: "PK",
  AUT: "AT",
  HUN: "HU",
  SES: "LU",
};

/** ISO 3166-1 alpha-2 for a Space-Track owner code, or null when no national
 *  flag applies (global / commercial / unknown owners). */
export function countryISO(code: string | null | undefined): string | null {
  if (!code) return null;
  return COUNTRY_ISO[code] ?? null;
}
