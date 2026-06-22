// Global test setup: jest-dom matchers + jsdom shims for the browser APIs the
// app's providers touch on mount. jsdom ships neither `fetch` nor `EventSource`,
// so the auth probe (/api/auth/me) and the alert SSE stream must no-op instead
// of throwing or hitting the network.

import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
});

// Every GET resolves to a 401 — AuthProvider reads it as "no session" (retry:0),
// which keeps the alert EventSource closed and the tree in a clean signed-out
// state without any real network call.
globalThis.fetch = vi.fn(
  async () => new Response(null, { status: 401 })
) as unknown as typeof fetch;

class FakeEventSource {
  close() {}
  addEventListener() {}
  removeEventListener() {}
}
globalThis.EventSource = FakeEventSource as unknown as typeof EventSource;
