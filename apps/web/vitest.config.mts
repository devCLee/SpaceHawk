import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

// Component tests run in jsdom with the React plugin (JSX + Fast Refresh-free
// transform). `@/…` mirrors the tsconfig path alias so test imports match app
// imports. Scoped to src so Cesium / Next build scripts are never picked up.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
