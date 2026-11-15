import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FakeEventSource, fakeFactory } from "@/test/fakeEventSource";
import { backoffMs, openSse, type SseMessage, type SseStatus } from "./sse";

const url = (seq: number | null) => `/events?after_seq=${seq ?? 0}`;

describe("openSse", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    FakeEventSource.reset();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("parses named events, tracks the last persisted seq and reconnects after it", async () => {
    const msgs: SseMessage[] = [];
    const refresh = vi.fn(() => Promise.resolve(true));
    const sub = openSse({
      url,
      events: ["metrics", "progress"],
      onMessage: (m) => msgs.push(m),
      factory: fakeFactory,
      refresh,
    });
    const es = FakeEventSource.last();
    expect(es.url).toBe("/events?after_seq=0");
    es.open();
    es.emit("metrics", { step: 200, values: { loss: 1 } }, 41);
    es.emit("progress", { step: 210 }); // ephemeral: no id
    es.emit("metrics", { step: 400, values: { loss: 0.5 } }, 42);
    expect(msgs.map((m) => [m.event, m.id])).toEqual([
      ["metrics", 41],
      ["progress", null],
      ["metrics", 42],
    ]);
    expect(sub.lastSeq()).toBe(42);

    es.fail(); // e.g. 401 after access token expiry
    await vi.advanceTimersByTimeAsync(0);
    expect(refresh).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(backoffMs(0));
    expect(FakeEventSource.instances).toHaveLength(2);
    expect(FakeEventSource.last().url).toBe("/events?after_seq=42");
    expect(es.closed).toBe(true);
    sub.close();
  });

  it("does not refresh the session when the stream dies because the page unloads (QC-e2e-07)", async () => {
    const refresh = vi.fn(() => Promise.resolve(true));
    let unloading = false;
    const sub = openSse({
      url,
      events: ["metrics"],
      onMessage: () => undefined,
      factory: fakeFactory,
      refresh,
      isUnloading: () => unloading,
    });
    const es = FakeEventSource.last();
    es.open();
    unloading = true; // reload / navigation: the browser aborts the stream
    es.fail();
    await vi.advanceTimersByTimeAsync(backoffMs(0) + 10);
    expect(refresh).not.toHaveBeenCalled();
    expect(FakeEventSource.instances).toHaveLength(1);
    expect(es.closed).toBe(true);
    sub.close();
  });

  it("ignores the transport error event on a named `error` listener (no empty notices)", () => {
    const msgs: SseMessage[] = [];
    const sub = openSse({
      url,
      events: ["error", "warning"],
      onMessage: (m) => msgs.push(m),
      factory: fakeFactory,
      refresh: () => Promise.resolve(true),
    });
    const es = FakeEventSource.last();
    es.open();
    es.transportErrorToListeners();
    es.emit("error", { code: "oom", message: "CUDA OOM" }, 3);
    expect(msgs.map((m) => m.event)).toEqual(["error"]);
    expect(msgs[0]?.data).toEqual({ code: "oom", message: "CUDA OOM" });
    sub.close();
  });

  it("reconnects when the heartbeat watchdog fires (silent connection)", async () => {
    const statuses: SseStatus[] = [];
    const sub = openSse({
      url,
      events: ["heartbeat"],
      onMessage: () => undefined,
      onStatus: (s) => statuses.push(s),
      factory: fakeFactory,
      watchdogMs: 45_000,
    });
    const es = FakeEventSource.last();
    es.open();
    await vi.advanceTimersByTimeAsync(30_000);
    es.emit("heartbeat", { kind: "heartbeat", ts: "x" });
    await vi.advanceTimersByTimeAsync(30_000); // 30s since last heartbeat: still fine
    expect(FakeEventSource.instances).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(16_000);
    expect(FakeEventSource.instances).toHaveLength(2);
    expect(es.closed).toBe(true);
    expect(statuses).toContain("reconnecting");
    sub.close();
  });

  it("leaves transient errors to the browser's own reconnect", async () => {
    const sub = openSse({ url, events: ["status"], onMessage: () => undefined, factory: fakeFactory });
    FakeEventSource.last().blip();
    await vi.advanceTimersByTimeAsync(5_000);
    expect(FakeEventSource.instances).toHaveLength(1);
    sub.close();
  });

  it("closes for good on `end`", async () => {
    const statuses: SseStatus[] = [];
    const msgs: string[] = [];
    openSse({
      url,
      events: ["end"],
      onMessage: (m) => msgs.push(m.event),
      onStatus: (s) => statuses.push(s),
      factory: fakeFactory,
    });
    const es = FakeEventSource.last();
    es.open();
    es.emit("end", { kind: "end", final_status: "succeeded" });
    await vi.advanceTimersByTimeAsync(120_000);
    expect(msgs).toEqual(["end"]);
    expect(es.closed).toBe(true);
    expect(FakeEventSource.instances).toHaveLength(1);
    expect(statuses.at(-1)).toBe("closed");
  });

  it("gives up after maxAttempts consecutive failures", async () => {
    const statuses: SseStatus[] = [];
    openSse({
      url,
      events: ["status"],
      onMessage: () => undefined,
      onStatus: (s) => statuses.push(s),
      factory: fakeFactory,
      maxAttempts: 2,
      refresh: () => Promise.resolve(false),
    });
    FakeEventSource.last().fail();
    await vi.advanceTimersByTimeAsync(backoffMs(0));
    FakeEventSource.last().fail();
    await vi.advanceTimersByTimeAsync(backoffMs(1));
    FakeEventSource.last().fail();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(statuses.at(-1)).toBe("failed");
    expect(FakeEventSource.instances).toHaveLength(3);
  });

  it("backoff grows exponentially and caps at 30 s", () => {
    expect([0, 1, 2, 3, 10].map(backoffMs)).toEqual([1000, 2000, 4000, 8000, 30000]);
  });
});
