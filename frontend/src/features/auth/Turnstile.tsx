import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";

interface TurnstileApi {
  render: (el: HTMLElement, opts: Record<string, unknown>) => string;
  reset: (id?: string) => void;
  remove: (id: string) => void;
}

declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}

const SCRIPT_SRC = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
let loading: Promise<void> | null = null;

function loadScript(): Promise<void> {
  if (window.turnstile) return Promise.resolve();
  loading ??= new Promise<void>((resolve, reject) => {
    const s = document.createElement("script");
    s.src = SCRIPT_SRC;
    s.async = true;
    s.defer = true;
    s.onload = () => {
      resolve();
    };
    s.onerror = () => {
      loading = null;
      reject(new Error("turnstile script failed"));
    };
    document.head.appendChild(s);
  });
  return loading;
}

/**
 * Cloudflare Turnstile widget, rendered only when `GET /auth/config` returns a site key.
 * Requires CSP `script-src https://challenges.cloudflare.com; frame-src https://challenges.cloudflare.com`.
 */
export function Turnstile({
  siteKey,
  onToken,
  resetSignal = 0,
}: {
  siteKey: string;
  onToken: (token: string | null) => void;
  resetSignal?: number;
}) {
  const { i18n } = useTranslation();
  const host = useRef<HTMLDivElement>(null);
  const widgetId = useRef<string | null>(null);
  const cb = useRef(onToken);
  cb.current = onToken;

  useEffect(() => {
    let cancelled = false;
    void loadScript()
      .then(() => {
        if (cancelled || !host.current || !window.turnstile) return;
        widgetId.current = window.turnstile.render(host.current, {
          sitekey: siteKey,
          language: i18n.language,
          callback: (token: string) => {
            cb.current(token);
          },
          "expired-callback": () => {
            cb.current(null);
          },
          "error-callback": () => {
            cb.current(null);
          },
        });
      })
      .catch(() => {
        cb.current(null);
      });
    return () => {
      cancelled = true;
      if (widgetId.current && window.turnstile) window.turnstile.remove(widgetId.current);
      widgetId.current = null;
    };
  }, [siteKey, i18n.language]);

  useEffect(() => {
    if (resetSignal > 0 && widgetId.current && window.turnstile) {
      window.turnstile.reset(widgetId.current);
      cb.current(null);
    }
  }, [resetSignal]);

  return <div ref={host} className="min-h-[65px]" />;
}
