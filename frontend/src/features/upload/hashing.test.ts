import { createHash } from "node:crypto";
import { describe, expect, it } from "vitest";
import { hashBlob, hashFile, partCount, partRange, READ_SLICE } from "./hashing";

function bytes(n: number, seed = 7): Uint8Array {
  const out = new Uint8Array(n);
  let x = seed;
  for (let i = 0; i < n; i += 1) {
    x = (x * 1103515245 + 12345) & 0x7fffffff;
    out[i] = x & 0xff;
  }
  return out;
}

const sha = (b: Uint8Array) => createHash("sha256").update(b).digest("hex");

describe("hashFile", () => {
  it("computes the whole-file and per-part SHA-256 in one pass (matches node:crypto)", async () => {
    const data = bytes(READ_SLICE * 2 + 12345); // spans several read slices
    const partSize = READ_SLICE + 1000; // part boundaries not aligned with slices
    const progress: number[] = [];
    const res = await hashFile(new Blob([data]), partSize, (b) => progress.push(b));
    expect(res.sha256).toBe(sha(data));
    expect(res.parts).toHaveLength(partCount(data.length, partSize));
    res.parts.forEach((h, i) => {
      const [s, e] = partRange(i + 1, data.length, partSize);
      expect(h).toBe(sha(data.slice(s, e)));
    });
    expect(progress.at(-1)).toBe(data.length);
    expect([...progress].sort((a, b) => a - b)).toEqual(progress);
  });

  it("handles a file smaller than one part and an empty file", async () => {
    const small = bytes(100);
    const r = await hashFile(new Blob([small]), 1024);
    expect(r.parts).toEqual([sha(small)]);
    const empty = await hashFile(new Blob([]), 1024);
    expect(empty.sha256).toBe(sha(new Uint8Array()));
    expect(empty.parts).toHaveLength(1);
  });

  it("stops when aborted", async () => {
    await expect(
      hashFile(new Blob([bytes(READ_SLICE * 2)]), READ_SLICE, undefined, () => true),
    ).rejects.toThrow("aborted");
  });

  it("hashBlob matches node:crypto", async () => {
    const data = bytes(READ_SLICE + 3);
    expect(await hashBlob(new Blob([data]))).toBe(sha(data));
  });

  it("partRange covers the file exactly", () => {
    expect(partRange(1, 10, 4)).toEqual([0, 4]);
    expect(partRange(3, 10, 4)).toEqual([8, 10]);
    expect(partCount(10, 4)).toBe(3);
    expect(partCount(0, 4)).toBe(1);
  });
});
