"use client";

// The tracked-debris layer + its risk analysis, fetched from the BFF and shared
// via React Query (mirrors useCatalog). Debris TLEs are slow-changing, so a long
// staleTime avoids refetching on remount.

import { useApiQuery } from "@/lib/api/useApiQuery";
import { queryKeys } from "@/lib/api/queryKeys";
import type { Debris, DebrisRiskSummary } from "@/lib/orbital-engine";

export function useDebris() {
  return useApiQuery<Debris[]>({
    queryKey: queryKeys.debris(),
    url: "/api/debris",
    options: { staleTime: 5 * 60_000 },
  });
}

export function useDebrisRisk() {
  return useApiQuery<DebrisRiskSummary>({
    queryKey: queryKeys.debrisRisk(),
    url: "/api/debris/risk",
    options: { staleTime: 5 * 60_000 },
  });
}
