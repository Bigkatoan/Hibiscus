import { defineConfig } from "vitest/config";

// Runs on Node 22 (WebCrypto, Request/Response are built in). The only Workers-specific import,
// `cloudflare:email`, is loaded lazily in routing mode and mocked in that single test.
export default defineConfig({
  test: {
    include: ["test/**/*.test.ts"],
    coverage: {
      provider: "v8",
      include: ["src/**/*.ts"],
      thresholds: { lines: 90, branches: 85, functions: 90, statements: 90 },
    },
  },
});
