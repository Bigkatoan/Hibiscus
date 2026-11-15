/**
 * Resilient Server-Sent Events subscription (ADR-0010):
 *  - persisted events carry `id:`; we track the highest seq and reconnect with `?after_seq=`
 *    (the browser also sends `Last-Event-ID` on its own automatic reconnects);
 *  - heartbeat watchdog: no message (heartbeat included) for `watchdogMs` (45 s) => reconnect;
 *  - an EventSource that is CLOSED by the browser (HTTP error, e.g. 401 after access-token expiry)
 *    triggers `POST /auth/refresh` and a reconnect with exponential backoff - except while the
 *    page is unloading (reload / navigation aborts the stream): a refresh fired then is aborted
 *    by the browser after the server already rotated the token (QC-e2e-07);
 *  - `event: end` closes the stream for good.
 */
import { refreshSession } from "./client";

export type SseStatus = "connecting" | "open" | "reconnecting" | "closed" | "failed";

export interface SseMessage {
  event: string;
  id: number | null;
  data: unknown;
}

export interface EventSourceLike {
  readonly readyState: number;
  onopen: ((this: EventSourceLike, ev: Event) => unknown) | null;
  onerror: ((this: EventSourceLike, ev: Event) => unknown) | null;
  addEventListener(type: string, listener: (ev: MessageEvent<string>) => void): void;
  close(): void;
}

export type EventSourceFactory = (url: string) => EventSourceLike;

const CLOSED = 2;

// Set on `pagehide` / `beforeunload`, cleared on `pageshow` (back/forward cache restore).
let pageUnloading = false;
if (typeof window !== "undefined" && typeof window.addEventListener === "function") {
  const mark = () => {
    pageUnloading = true;
  };
  window.addEventListener("pagehide", mark);
  window.addEventListener("beforeunload", mark);
  window.addEventListener("pageshow", () => {
    pageUnloading = false;
  });
}

/** True while the document is being unloaded (reload, navigation away). */
export function isPageUnloading(): boolean {
  return pageUnloading;
}

export const defaultEventSourceFactory: EventSourceFactory = (url) =>
  new EventSource(url, { withCredentials: true }) as unknown as EventSourceLike;

export interface SseOptions {
  /** Builds the stream URL; receives the last persisted seq seen (null on first connect). */
  url: (afterSeq: number | null) => string;
  /** SSE `event:` names to listen to (unnamed `message` events are ignored by the contract). */
  events: readonly string[];
  onMessage: (msg: SseMessage) => void;
  onStatus?: (status: SseStatus) => void;
  watchdogMs?: number;
  maxAttempts?: number;
  factory?: EventSourceFactory;
  refresh?: () => Promise<boolean>;
  /** Whether the page is unloading (no refresh / reconnect then). */
  isUnloading?: () => boolean;
  /** Start seq (e.g. after loading history via REST). */
  initialSeq?: number | null;
}

export interface SseSubscription {
  close: () => void;
  lastSeq: () => number | null;
}

export function backoffMs(attempt: number): number {
  return Math.min(30_000, 1000 * 2 ** Math.max(0, attempt));
}

export function openSse(options: SseOptions): SseSubscription {
  const {
    url,
    events,
    onMessage,
    onStatus,
    watchdogMs = 45_000,
    maxAttempts = 30,
    factory = defaultEventSourceFactory,
    refresh = refreshSession,
    isUnloading = isPageUnloading,
  } = options;

  let lastSeq: number | null = options.initialSeq ?? null;
  let es: EventSourceLike | null = null;
  let stopped = false;
  let attempts = 0;
  let watchdog: ReturnType<typeof setTimeout> | null = null;
  let retryTimer: ReturnType<typeof setTimeout> | null = null;

  const setStatus = (s: SseStatus) => onStatus?.(s);

  const clearWatchdog = () => {
    if (watchdog !== null) clearTimeout(watchdog);
    watchdog = null;
  };

  const armWatchdog = () => {
    clearWatchdog();
    watchdog = setTimeout(() => {
      // Silent connection (proxy dropped it without FIN): force a fresh connection.
      reconnect(0);
    }, watchdogMs);
  };

  const teardown = () => {
    clearWatchdog();
    if (es) {
      es.onopen = null;
      es.onerror = null;
      es.close();
      es = null;
    }
  };

  const reconnect = (delay: number) => {
    teardown();
    if (stopped) return;
    setStatus("reconnecting");
    if (retryTimer !== null) clearTimeout(retryTimer);
    retryTimer = setTimeout(() => {
      retryTimer = null;
      connect();
    }, delay);
  };

  const handle = (name: string) => (ev: MessageEvent<string>) => {
    if (stopped) return;
    // A named `error` listener also receives EventSource's own transport error (a plain Event
    // without data); that is handled by onerror and must not surface as an empty server notice.
    if (typeof (ev as { data?: unknown }).data !== "string") return;
    armWatchdog();
    attempts = 0;
    let data: unknown = null;
    try {
      data = JSON.parse(ev.data);
    } catch {
      data = ev.data;
    }
    const id = ev.lastEventId && /^\d+$/.test(ev.lastEventId) ? Number(ev.lastEventId) : null;
    if (id !== null && (lastSeq === null || id > lastSeq)) lastSeq = id;
    onMessage({ event: name, id, data });
    if (name === "end") {
      stopped = true;
      teardown();
      setStatus("closed");
    }
  };

  function connect(): void {
    if (stopped) return;
    setStatus(attempts === 0 ? "connecting" : "reconnecting");
    const source = factory(url(lastSeq));
    es = source;
    source.onopen = () => {
      setStatus("open");
      armWatchdog();
    };
    source.onerror = () => {
      if (stopped || es !== source) return;
      if (source.readyState === CLOSED) {
        if (isUnloading()) {
          // The page is going away: the error is the aborted stream, not an expired token.
          teardown();
          return;
        }
        attempts += 1;
        if (attempts > maxAttempts) {
          teardown();
          stopped = true;
          setStatus("failed");
          return;
        }
        const delay = backoffMs(attempts - 1);
        teardown();
        setStatus("reconnecting");
        // The browser gave up (HTTP error). The likely cause is an expired access token.
        void refresh().finally(() => {
          if (!stopped) reconnect(delay);
        });
      } else {
        setStatus("reconnecting");
      }
    };
    for (const name of events) source.addEventListener(name, handle(name));
    armWatchdog();
  }

  connect();

  return {
    close: () => {
      stopped = true;
      if (retryTimer !== null) clearTimeout(retryTimer);
      teardown();
      setStatus("closed");
    },
    lastSeq: () => lastSeq,
  };
}
