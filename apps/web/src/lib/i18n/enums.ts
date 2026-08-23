// Display labels for enum values that are ALSO sent to the backend as query
// parameters. The raw value (PAYLOAD, NEW, …) is the API contract and must never
// change; only its rendered label is localized. Look the label up here, keep the
// value in the array / request.

import { t } from "./t";

// Catalog object_type — sent to the engine /catalog as `object_type`.
const OBJECT_TYPE_LABEL: Record<string, string> = {
  "": "모든 유형",
  PAYLOAD: "탑재체",
  "ROCKET BODY": "로켓 본체",
  DEBRIS: "잔해",
  UNKNOWN: "미상",
};

export function objectTypeLabel(value: string): string {
  return OBJECT_TYPE_LABEL[value] ?? value;
}

// Alert status filter — sent to the engine /alerts/log as `status`.
const ALERT_STATUS_LABEL: Record<string, string> = {
  NEW: "신규",
  ACK: "확인됨",
  DISMISSED: "무시됨",
};

export function alertStatusLabel(value: string): string {
  return ALERT_STATUS_LABEL[value] ?? value;
}

// Maneuver classification — the engine's ManeuverResponse.maneuver_type.
// Labels live in messages.ts (maneuver.type.*); this map keys them by raw value.
const MANEUVER_TYPE_LABEL: Record<string, string> = {
  STATION_KEEPING: t("maneuver.type.stationKeeping"),
  ORBIT_RAISE: t("maneuver.type.orbitRaise"),
  ORBIT_LOWER: t("maneuver.type.orbitLower"),
  PHASING: t("maneuver.type.phasing"),
  RPO: t("maneuver.type.rpo"),
  UNKNOWN: t("maneuver.type.unknown"),
};

export function maneuverTypeLabel(value: string): string {
  return MANEUVER_TYPE_LABEL[value] ?? value;
}
