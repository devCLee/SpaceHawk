"use client";

// The full globe catalog (TleObjects), fetched once from /api/catalog/all and
// shared via the React Query cache across the globe and the country/constellation
// panels (one network request, not three). TLEs are slow-changing and live
// positions arrive over the SSE state stream, so a long staleTime is safe and
// avoids refetching on remount / navigation.

import { useApiQuery } from "@/lib/api/useApiQuery";
import { queryKeys } from "@/lib/api/queryKeys";
import type { TleObject } from "@/app/utils/sgp4FromTle";

export function useCatalog() {
  return useApiQuery<TleObject[]>({
    queryKey: queryKeys.catalogAll(),
    url: "/api/catalog/all",
    options: { staleTime: 5 * 60_000 },
  });
}
