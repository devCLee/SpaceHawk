// Central query-key registry (house convention — see team's API_URL). Keys are
// arrays/factories so related caches invalidate together. URLs are the
// same-origin BFF paths the keys map to.

import type { CatalogQuery } from "@/lib/orbital-engine";

export const queryKeys = {
  // GET /api/catalog
  catalog: (query: CatalogQuery) => ["catalog", "list", query] as const,
  // GET /api/catalog/{id}
  catalogDetail: (objectId: string) =>
    ["catalog", "detail", objectId] as const,
  // GET /api/conjunctions
  conjunctions: () => ["conjunctions", "list"] as const,
};
