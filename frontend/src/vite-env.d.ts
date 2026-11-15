/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "1" only in `--mode mock` (see .env.mock and src/mock/browser.ts). */
  readonly VITE_HIBISCUS_MOCK?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
