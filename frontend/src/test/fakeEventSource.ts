import type { EventSourceLike } from "@/api/sse";

/** In-memory EventSource double (jsdom has none). Tests drive it with emit/open/fail. */
export class FakeEventSource implements EventSourceLike {
  static instances: FakeEventSource[] = [];
  readyState = 0;
  onopen: ((this: EventSourceLike, ev: Event) => unknown) | null = null;
  onerror: ((this: EventSourceLike, ev: Event) => unknown) | null = null;
  closed = false;
  private listeners = new Map<string, ((ev: MessageEvent<string>) => void)[]>();

  constructor(readonly url: string) {
    FakeEventSource.instances.push(this);
  }

  static reset(): void {
    FakeEventSource.instances = [];
  }

  static last(): FakeEventSource {
    const l = FakeEventSource.instances.at(-1);
    if (!l) throw new Error("no EventSource created");
    return l;
  }

  addEventListener(type: string, listener: (ev: MessageEvent<string>) => void): void {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }

  close(): void {
    this.closed = true;
    this.readyState = 2;
  }

  open(): void {
    this.readyState = 1;
    this.onopen?.call(this, new Event("open"));
  }

  emit(type: string, data: unknown, id?: number): void {
    const ev = new MessageEvent<string>(type, {
      data: JSON.stringify(data),
      lastEventId: id === undefined ? "" : String(id),
    });
    for (const l of this.listeners.get(type) ?? []) l(ev);
  }

  /** Browser gave up (HTTP error): readyState CLOSED + error event. */
  fail(): void {
    this.readyState = 2;
    this.onerror?.call(this, new Event("error"));
  }

  /** Real EventSources also dispatch their transport error to `error` listeners (no data). */
  transportErrorToListeners(): void {
    const ev = new Event("error") as MessageEvent<string>;
    for (const l of this.listeners.get("error") ?? []) l(ev);
  }

  /** Transient error: browser will reconnect itself. */
  blip(): void {
    this.readyState = 0;
    this.onerror?.call(this, new Event("error"));
  }
}

export const fakeFactory = (url: string) => new FakeEventSource(url);
