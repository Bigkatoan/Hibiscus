import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { openSse, type SseMessage } from "@/api/sse";
import * as f from "@/test/fixtures";
import { createMockEventSource } from "./mockEventSource";

describe("mock-mode EventSource", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("streams progress/metrics/log for a running run through the real SSE client", () => {
    const Mock = createMockEventSource({ runs: { [f.IDS.run]: f.run }, tickMs: 1000 });
    const got: SseMessage[] = [];
    const statuses: string[] = [];
    const sub = openSse({
      url: () => `/api/v1/runs/${f.IDS.run}/events?after_seq=17`,
      events: ["progress", "metrics", "log", "telemetry", "heartbeat", "end"],
      onMessage: (m) => got.push(m),
      onStatus: (s) => statuses.push(s),
      factory: (url) => new Mock(url),
      refresh: () => Promise.resolve(true),
    });
    vi.advanceTimersByTime(3100);
    expect(statuses).toContain("open");
    const progress = got.filter((m) => m.event === "progress");
    expect(progress).toHaveLength(3);
    expect((progress[2]?.data as { step: number }).step).toBeGreaterThan(f.run.progress.current_step);
    const metrics = got.filter((m) => m.event === "metrics");
    expect(metrics.map((m) => m.id)).toEqual([18, 19, 20]);
    expect(got.some((m) => m.event === "log")).toBe(true);
    expect(got.some((m) => m.event === "heartbeat")).toBe(true);
    sub.close();
  });

  it("other streams only get heartbeats", () => {
    const Mock = createMockEventSource({ runs: {}, heartbeatMs: 1000 });
    const es = new Mock(`/api/v1/workspaces/${f.IDS.ws}/events`);
    const seen: string[] = [];
    es.addEventListener("heartbeat", () => seen.push("hb"));
    es.addEventListener("progress", () => seen.push("progress"));
    vi.advanceTimersByTime(2500);
    expect(seen).toEqual(["hb", "hb", "hb"]);
    es.close();
    vi.advanceTimersByTime(5000);
    expect(seen).toHaveLength(3);
  });
});
