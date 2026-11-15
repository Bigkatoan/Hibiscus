/**
 * Incremental SHA-256 of large files (multi-GB) in bounded memory.
 * Runs inside a Web Worker in the browser (`hash.worker.ts`); the same code is used directly in
 * tests and as a main-thread fallback when Workers are unavailable.
 */
import { createSHA256 } from "hash-wasm";

export const MiB = 1024 * 1024;
export const MAX_PART_SIZE = 64 * MiB;
export const MIN_PART_SIZE = 5 * MiB;
/** Slice read per step; keeps memory flat regardless of part size. */
export const READ_SLICE = 8 * MiB;

export interface FileHashes {
  sha256: string;
  partSize: number;
  parts: string[];
}

export async function readBlob(blob: Blob): Promise<Uint8Array> {
  if (typeof blob.arrayBuffer === "function") return new Uint8Array(await blob.arrayBuffer());
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      resolve(new Uint8Array(reader.result as ArrayBuffer));
    };
    reader.onerror = () => {
      reject(reader.error ?? new Error("read failed"));
    };
    reader.readAsArrayBuffer(blob);
  });
}

export class HashAbortedError extends Error {
  constructor() {
    super("hashing aborted");
    this.name = "HashAbortedError";
  }
}

/**
 * One pass over the file computing the whole-file digest and one digest per `partSize` part.
 * `onProgress(bytesHashed)` is called after each slice.
 */
export async function hashFile(
  file: Blob,
  partSize: number,
  onProgress?: (bytes: number) => void,
  isAborted?: () => boolean,
): Promise<FileHashes> {
  if (partSize <= 0) throw new Error("partSize must be > 0");
  const whole = await createSHA256();
  const part = await createSHA256();
  whole.init();
  part.init();
  const parts: string[] = [];
  let offset = 0;
  let partFilled = 0;
  const size = file.size;
  while (offset < size) {
    if (isAborted?.()) throw new HashAbortedError();
    const take = Math.min(READ_SLICE, size - offset, partSize - partFilled);
    const bytes = await readBlob(file.slice(offset, offset + take));
    whole.update(bytes);
    part.update(bytes);
    offset += take;
    partFilled += take;
    if (partFilled === partSize || offset === size) {
      parts.push(part.digest("hex"));
      part.init();
      partFilled = 0;
    }
    onProgress?.(offset);
  }
  if (size === 0) parts.push(part.digest("hex"));
  return { sha256: whole.digest("hex"), partSize, parts };
}

/** SHA-256 of a single blob (used to re-hash a part if the server's part_size differs). */
export async function hashBlob(blob: Blob): Promise<string> {
  const h = await createSHA256();
  h.init();
  let offset = 0;
  while (offset < blob.size) {
    const take = Math.min(READ_SLICE, blob.size - offset);
    h.update(await readBlob(blob.slice(offset, offset + take)));
    offset += take;
  }
  return h.digest("hex");
}

export function partCount(size: number, partSize: number): number {
  return Math.max(1, Math.ceil(size / partSize));
}

/** Byte range [start, end) of 1-based part `n`. */
export function partRange(n: number, size: number, partSize: number): [number, number] {
  const start = (n - 1) * partSize;
  return [start, Math.min(size, start + partSize)];
}
