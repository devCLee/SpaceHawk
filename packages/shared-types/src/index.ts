// Public entrypoint for the generated Orbital Engine contract.
//
// `orbital-engine.ts` is auto-generated from the FastAPI OpenAPI document
// (`openapi.json`) by `npm run generate`. Do not edit it by hand; regenerate it
// from the engine via the root `gen:client` script whenever the API changes.

import createClient, { type ClientOptions } from "openapi-fetch";
import type { paths } from "./orbital-engine.js";

export type { paths } from "./orbital-engine.js";
export type { components, operations } from "./orbital-engine.js";

/**
 * Create a typed client for the Orbital Engine API. The web/BFF tier uses this to
 * call the internal Python service with full path/response type-safety.
 */
export function createOrbitalEngineClient(options: ClientOptions) {
  return createClient<paths>(options);
}
