import "./lib/localeGuard";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app/App";
import { AppErrorBoundary } from "./app/ErrorBoundary";
import { initI18n } from "./lib/i18n";
import "./index.css";

async function boot(): Promise<void> {
  // Mock mode only (vite --mode mock); statically false — and tree-shaken — in production builds.
  if (import.meta.env.VITE_HIBISCUS_MOCK === "1") {
    const { startMockWorker } = await import("./mock/browser");
    await startMockWorker();
  }
  initI18n();
  const root = document.getElementById("root");
  if (root) {
    createRoot(root).render(
      <StrictMode>
        <AppErrorBoundary>
          <App />
        </AppErrorBoundary>
      </StrictMode>,
    );
  }
}

void boot();
