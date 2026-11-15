/// <reference types="vitest/config" />
import { readFileSync } from "node:fs";
import { fileURLToPath, URL } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

// Dev server proxies /api to the developer stack (docker compose dev profile, localhost:8080).
// Never point it at 127.0.0.1:18000 / :8000 (public via Cloudflare Tunnel / LeLab).
const apiTarget = process.env.HIBISCUS_DEV_API ?? "http://localhost:8080";

/** Mock mode only: serve/emit MSW's service worker without committing it to public/. */
function mswWorker(): Plugin {
  const file = fileURLToPath(new URL("./node_modules/msw/lib/mockServiceWorker.js", import.meta.url));
  return {
    name: "hibiscus-msw-worker",
    configureServer(server) {
      server.middlewares.use("/mockServiceWorker.js", (_req, res) => {
        res.setHeader("Content-Type", "text/javascript");
        res.end(readFileSync(file));
      });
    },
    generateBundle() {
      this.emitFile({ type: "asset", fileName: "mockServiceWorker.js", source: readFileSync(file) });
    },
  };
}

export default defineConfig(({ mode }) => ({
  plugins: mode === "mock" ? [react(), mswWorker()] : [react()],
  // Mock mode must not depend on an untracked .env.mock (`.env.*` is git-ignored): fresh checkouts
  // and worktrees otherwise build a "mock" bundle that talks to the real /api.
  define: mode === "mock" ? { "import.meta.env.VITE_HIBISCUS_MOCK": JSON.stringify("1") } : {},
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    proxy: { "/api": { target: apiTarget, changeOrigin: false } },
  },
  build: {
    outDir: mode === "mock" ? "dist-mock" : "dist",
    sourcemap: false,
    target: "es2022",
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: {
        manualChunks: {
          // Own chunk, imported first by the entry: it must run before uPlot reads
          // navigator.language at module load (QC N-3). Inlined into the entry chunk it would run
          // after every vendor chunk the entry imports.
          "locale-guard": ["./src/lib/localeGuard.ts"],
          react: ["react", "react-dom", "react-router-dom"],
          query: ["@tanstack/react-query", "openapi-fetch"],
          charts: ["uplot"],
          forms: ["react-hook-form", "zod", "@hookform/resolvers"],
        },
      },
    },
  },
  worker: { format: "es" },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
    restoreMocks: true,
    testTimeout: 20000,
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "src/api/generated/**",
        "src/test/**",
        "src/**/*.test.{ts,tsx}",
        "src/main.tsx",
        "src/**/*.worker.ts",
        "src/vite-env.d.ts",
      ],
      reporter: ["text-summary", "json-summary"],
      thresholds: { lines: 70 },
    },
  },
}));
