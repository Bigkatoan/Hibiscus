/**
 * Browser mock mode: an in-page EventSource so the live views work without a backend. MSW 2.7
 * cannot intercept EventSource, so without this every run page / AppShell stream hit the dev
 * server, failed, and the SSE layer went into its refresh + reconnect loop.
 *
 *  - `/runs/<running id>/events`: progress, metrics (loss, lr), a log line and a GPU sample every
 *    `tickMs`, plus heartbeats; the step advances until `total_steps`, then `end`.
 *  - any other stream (workspace events, finished runs): heartbeats only.
 */
import type { Schemas } from "@/api/client";

type S = Schemas;

type Listener = (ev: MessageEvent<string>) => void;

export interface MockStreamOptions {
  /** Runs that stream (keyed by id); other run ids only get heartbeats. */
  runs: Record<string, S["Run"]>;
  tickMs?: number;
  heartbeatMs?: number;
  now?: () => Date;
}

export function createMockEventSource(options: MockStreamOptions) {
  const { runs, tickMs = 1000, heartbeatMs = 15_000, now = () => new Date() } = options;

  return class MockEventSource {
    static readonly CONNECTING = 0;
    static readonly OPEN = 1;
    static readonly CLOSED = 2;
    readyState = 0;
    onopen: ((ev: Event) => unknown) | null = null;
    onerror: ((ev: Event) => unknown) | null = null;
    onmessage: ((ev: MessageEvent<string>) => unknown) | null = null;
    readonly url: string;
    readonly withCredentials: boolean;
    private listeners = new Map<string, Listener[]>();
    private timers: ReturnType<typeof setInterval>[] = [];
    private seq: number;

    constructor(url: string | URL, init?: { withCredentials?: boolean }) {
      this.url = String(url);
      this.withCredentials = !!init?.withCredentials;
      const u = new URL(this.url, "http://mock.local");
      this.seq = Number(u.searchParams.get("after_seq") ?? "0") || 0;
      const runMatch = /\/runs\/([^/]+)\/events$/.exec(u.pathname);
      const run = runMatch ? runs[runMatch[1] ?? ""] : undefined;
      setTimeout(() => {
        if (this.readyState === 2) return;
        this.readyState = 1;
        this.onopen?.(new Event("open"));
        this.emit("heartbeat", { ts: now().toISOString() });
        this.timers.push(
          setInterval(() => {
            this.emit("heartbeat", { ts: now().toISOString() });
          }, heartbeatMs),
        );
        if (run?.status === "running") this.streamRun(run);
      }, 0);
    }

    private streamRun(run: S["Run"]): void {
      let step = run.progress.current_step;
      const total = run.progress.total_steps;
      const perTick = Math.max(1, Math.round((run.progress.steps_per_s ?? 9) * (tickMs / 1000)));
      let offset = 4096;
      this.timers.push(
        setInterval(() => {
          if (step >= total) {
            this.emit("end", { final_status: "succeeded" });
            this.close();
            return;
          }
          step = Math.min(total, step + perTick);
          const ts = now().toISOString();
          const loss = 0.25 + 2 * Math.exp(-step / 1500) + 0.02 * Math.sin(step / 37);
          const lr = 1e-5 * Math.min(1, step / 500);
          const sps = run.progress.steps_per_s ?? 9;
          this.emit("progress", {
            kind: "progress",
            step,
            total_steps: total,
            steps_per_s: sps,
            eta_s: Math.round((total - step) / sps),
            ts,
          });
          this.emit(
            "metrics",
            { kind: "metrics", step, values: { loss, lr, grad_norm: 3 * loss }, ts },
            true,
          );
          const line = `step:${step} smpl:${step * 8} ep:${Math.floor(step / 300)} loss:${loss.toFixed(3)} lr:${lr.toExponential(1)}`;
          this.emit("log", { kind: "log", byte_offset: offset, lines: [line] });
          offset += line.length + 1;
          this.emit("telemetry", {
            gpu_id: run.gpu_id ?? "cuda0",
            ts,
            util_pct: 80 + Math.round(10 * Math.random()),
            mem_used_mb: 2100,
            mem_total_mb: 12288,
            temperature_c: 64,
            power_w: 141,
          });
        }, tickMs),
      );
    }

    private emit(type: string, data: unknown, persisted = false): void {
      if (this.readyState !== 1) return;
      if (persisted) this.seq += 1;
      const ev = new MessageEvent<string>(type, {
        data: JSON.stringify(data),
        lastEventId: persisted ? String(this.seq) : "",
      });
      for (const l of this.listeners.get(type) ?? []) l(ev);
    }

    addEventListener(type: string, listener: Listener): void {
      this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
    }

    removeEventListener(type: string, listener: Listener): void {
      this.listeners.set(
        type,
        (this.listeners.get(type) ?? []).filter((l) => l !== listener),
      );
    }

    close(): void {
      this.readyState = 2;
      for (const t of this.timers) clearInterval(t);
      this.timers = [];
    }
  };
}
