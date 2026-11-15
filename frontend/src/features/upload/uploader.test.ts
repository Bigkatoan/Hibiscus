import { File as NodeFile } from "node:buffer";
import { createHash } from "node:crypto";
import { describe, expect, it } from "vitest";
import { fakeUploadServer } from "@/test/fakeUploadServer";
import { server } from "@/test/server";
import * as f from "@/test/fixtures";
import { inlineHasher } from "./hasher";
import {
  ChunkedUploader,
  fetchTransport,
  inferArchiveFormat,
  retryDelayMs,
  xhrTransport,
  type UploadPhase,
} from "./uploader";

function data(n: number): Uint8Array {
  const out = new Uint8Array(n);
  for (let i = 0; i < n; i += 1) out[i] = (i * 31 + 7) & 0xff;
  return out;
}

const noSleep = () => Promise.resolve();
const target = { workspaceId: f.IDS.ws, newDatasetName: "so101" };

// Node's File (not jsdom's): under vitest the fetch/Request stack is Node's (undici), which only
// understands its own Blob type. In browsers there is a single Blob implementation.
function file(bytes: Uint8Array, name = "Picknplace.rar"): File {
  return new NodeFile([bytes], name, {
    type: "application/octet-stream",
    lastModified: 1,
  }) as unknown as File;
}

describe("ChunkedUploader (against a stateful fake of the upload API)", () => {
  it("uploads every part with its SHA-256 and completes (XHR transport)", async () => {
    const bytes = data(2500);
    const fake = fakeUploadServer(bytes, { partSize: 1000 });
    server.use(...fake.handlers);
    document.cookie = "hb_csrf=csrf-token-value-0123456789abcdef0123; path=/";
    const up = new ChunkedUploader(file(bytes), target, {
      hasher: inlineHasher,
      transport: xhrTransport,
      sleep: noSleep,
      cacheHashes: false,
    });
    const phases: UploadPhase[] = [];
    up.subscribe((s) => {
      if (phases.at(-1) !== s.phase) phases.push(s.phase);
    });
    const res = await up.start();
    expect(res?.dataset.id).toBe(f.IDS.dataset);
    expect(fake.store.size).toBe(3);
    expect([...fake.store.values()].map((b) => b.length)).toEqual([1000, 1000, 500]);
    expect(up.state.uploadedBytes).toBe(2500);
    expect(up.state.partsDone).toBe(3);
    expect(phases).toEqual(["idle", "hashing", "initializing", "uploading", "completing", "done"]);
    expect(fake.log).toContain("init:idem");
    expect(fake.log.filter((l) => l.startsWith("csrf:"))).toHaveLength(3);
  });

  it("resumes: only parts missing on the server are sent", async () => {
    const bytes = data(3000);
    const fake = fakeUploadServer(bytes, { partSize: 1000, existingParts: [1, 3] });
    server.use(...fake.handlers);
    const up = new ChunkedUploader(file(bytes), target, {
      hasher: inlineHasher,
      transport: fetchTransport,
      sleep: noSleep,
      cacheHashes: false,
    });
    await up.start();
    expect(up.state.resumed).toBe(true);
    expect(fake.log.filter((l) => l.startsWith("put:"))).toEqual(["put:2"]);
    expect(up.state.phase).toBe("done");
  });

  it("retries 5xx with backoff and re-hashes once on checksum mismatch", async () => {
    const bytes = data(2000);
    const fake = fakeUploadServer(bytes, { partSize: 1000, flaky: { 1: 2 }, corruptOnce: [2] });
    server.use(...fake.handlers);
    const delays: number[] = [];
    const up = new ChunkedUploader(file(bytes), target, {
      hasher: inlineHasher,
      transport: fetchTransport,
      sleep: (ms) => {
        delays.push(ms);
        return Promise.resolve();
      },
      concurrency: 1,
      cacheHashes: false,
    });
    await up.start();
    expect(up.state.phase).toBe("done");
    expect(fake.attempts.get(1)).toBe(3);
    expect(fake.attempts.get(2)).toBe(2);
    expect(delays).toEqual([1000, 2000]);
  });

  it("re-sends parts the server reports missing on complete", async () => {
    const bytes = data(2000);
    const fake = fakeUploadServer(bytes, { partSize: 1000, missingOnComplete: [2] });
    server.use(...fake.handlers);
    const up = new ChunkedUploader(file(bytes), target, {
      hasher: inlineHasher,
      transport: fetchTransport,
      sleep: noSleep,
      cacheHashes: false,
    });
    await up.start();
    expect(up.state.phase).toBe("done");
    expect(fake.getCompletes()).toBe(2);
    expect(fake.log.filter((l) => l === "put:2")).toHaveLength(2);
  });

  it("fails with the server code after exhausting retries; resume continues later", async () => {
    const bytes = data(1500);
    const fake = fakeUploadServer(bytes, { partSize: 1000, flaky: { 2: 3 } });
    server.use(...fake.handlers);
    const up = new ChunkedUploader(file(bytes), target, {
      hasher: inlineHasher,
      transport: fetchTransport,
      sleep: noSleep,
      maxAttempts: 2,
      cacheHashes: false,
    });
    expect(await up.start()).toBeNull();
    expect(up.state.phase).toBe("error");
    expect(up.state.error?.code).toBe("service_unavailable");
    // network recovers: resume sends only part 2
    const res = await up.start();
    expect(res).not.toBeNull();
    expect(fake.log.filter((l) => l === "put:1")).toHaveLength(1);
  });

  it("uses the server's part_size when it differs from the requested one", async () => {
    const bytes = data(2600);
    const fake = fakeUploadServer(bytes, { partSize: 700 });
    server.use(...fake.handlers);
    const up = new ChunkedUploader(file(bytes), target, {
      hasher: inlineHasher,
      transport: fetchTransport,
      sleep: noSleep,
      cacheHashes: false,
    });
    await up.start();
    expect(fake.store.size).toBe(4);
    const whole = createHash("sha256").update(bytes).digest("hex");
    expect(up.state.session?.sha256).toBe(whole);
  });

  it("abort deletes the session", async () => {
    const bytes = data(1000);
    const fake = fakeUploadServer(bytes, { partSize: 1000 });
    server.use(...fake.handlers);
    const up = new ChunkedUploader(file(bytes), target, {
      hasher: inlineHasher,
      transport: fetchTransport,
      sleep: noSleep,
      cacheHashes: false,
    });
    await up.start();
    await up.abort();
    expect(up.state.phase).toBe("aborted");
  });

  it("infers archive formats and retry delays", () => {
    expect(
      ["a.zip", "a.tar.gz", "a.tgz", "a.tar.zst", "a.tar", "A.RAR", "a.7z"].map(inferArchiveFormat),
    ).toEqual(["zip", "tar.gz", "tar.gz", "tar.zst", "tar", "rar", null]);
    expect([0, 1, 5, 10].map((a) => retryDelayMs(a))).toEqual([1000, 2000, 32000, 60000]);
    expect(retryDelayMs(0, 7)).toBe(7000);
  });
});
