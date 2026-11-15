/**
 * Hibiscus Station UI build target (docs/spec/station.md §6, §10 B1).
 *
 *   vite -c vite.station.config.ts                       dev, proxies /api (+ WebSockets) to 127.0.0.1:18210
 *   vite -c vite.station.config.ts --mode station-mock   dev without a backend (MSW + in-page mock station)
 *   vite build -c vite.station.config.ts                 → dist-station/ (copied into the station wheel)
 *
 * The server SPA (vite.config.ts) is untouched; both share src/components, src/lib and public/.
 */
import { readFileSync, renameSync, existsSync } from "node:fs";
import { fileURLToPath, URL } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig, type HttpProxy, type Plugin } from "vite";

const stationTarget = process.env.HIBISCUS_STATION_API ?? "http://127.0.0.1:18210";

/** Mock mode only: serve/emit MSW's service worker without committing it to public/. */
function mswWorker(): Plugin {
  const file = fileURLToPath(new URL("./node_modules/msw/lib/mockServiceWorker.js", import.meta.url));
  return {
    name: "station-msw-worker",
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

/** Serve station.html at "/" (and every SPA route) in dev, and emit it as index.html. */
function stationIndex(outDir: string): Plugin {
  return {
    name: "station-index",
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        const url = req.url ?? "/";
        const isAsset =
          url.includes(".") ||
          url.startsWith("/@") ||
          url.startsWith("/src/") ||
          url.startsWith("/node_modules/") ||
          url.startsWith("/api/") ||
          url.startsWith("/auth");
        if (!isAsset) req.url = "/station.html";
        next();
      });
    },
    closeBundle() {
      const from = fileURLToPath(new URL(`./${outDir}/station.html`, import.meta.url));
      const to = fileURLToPath(new URL(`./${outDir}/index.html`, import.meta.url));
      if (existsSync(from)) renameSync(from, to);
    },
  };
}

/** Present proxied requests (HTTP and WebSocket upgrades) as coming from the Station origin. */
function sameOrigin(proxy: HttpProxy.Server): void {
  const origin = new URL(stationTarget).origin;
  proxy.on("proxyReq", (req) => {
    if (req.getHeader("origin")) req.setHeader("origin", origin);
  });
  proxy.on("proxyReqWs", (req) => {
    req.setHeader("origin", origin);
  });
}

export default defineConfig(({ mode }) => {
  const mock = mode === "station-mock";
  const outDir = mock ? "dist-station-mock" : "dist-station";
  return {
    plugins: mock ? [react(), mswWorker(), stationIndex(outDir)] : [react(), stationIndex(outDir)],
    define: mock ? { "import.meta.env.VITE_STATION_MOCK": JSON.stringify("1") } : {},
    resolve: {
      alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
    },
    server: {
      host: "127.0.0.1",
      port: 18211,
      strictPort: true,
      // Station only accepts its own Host and Origin (§8): the proxy rewrites both to the target, so
      // log in through the dev server with http://127.0.0.1:18211/auth?t=<token> (`hibiscus-station url`).
      proxy: {
        "/api": { target: stationTarget, changeOrigin: true, ws: true, configure: sameOrigin },
        "/auth": { target: stationTarget, changeOrigin: true, configure: sameOrigin },
      },
    },
    preview: { host: "127.0.0.1", port: 18212, strictPort: true },
    build: {
      outDir,
      emptyOutDir: true,
      sourcemap: false,
      target: "es2022",
      chunkSizeWarningLimit: 900,
      rollupOptions: {
        input: fileURLToPath(new URL("./station.html", import.meta.url)),
        output: {
          manualChunks: {
            react: ["react", "react-dom", "react-router-dom"],
            query: ["@tanstack/react-query"],
            charts: ["uplot"],
          },
        },
      },
    },
  };
});
