import { hashFile, HashAbortedError, type FileHashes } from "./hashing";

export type Hasher = (
  file: Blob,
  partSize: number,
  onProgress: (bytes: number) => void,
  signal: AbortSignal,
) => Promise<FileHashes>;

type WorkerReply =
  | { type: "progress"; bytes: number }
  | { type: "done"; result: FileHashes }
  | { type: "aborted" }
  | { type: "error"; message: string };

/** Hash in a dedicated Web Worker so multi-GB files do not block the UI thread. */
export const workerHasher: Hasher = (file, partSize, onProgress, signal) =>
  new Promise<FileHashes>((resolve, reject) => {
    const worker = new Worker(new URL("./hash.worker.ts", import.meta.url), { type: "module" });
    const finish = () => {
      worker.terminate();
    };
    signal.addEventListener(
      "abort",
      () => {
        worker.postMessage({ type: "abort" });
        finish();
        reject(new HashAbortedError());
      },
      { once: true },
    );
    worker.onmessage = (ev: MessageEvent<WorkerReply>) => {
      const msg = ev.data;
      if (msg.type === "progress") onProgress(msg.bytes);
      else if (msg.type === "done") {
        finish();
        resolve(msg.result);
      } else if (msg.type === "aborted") {
        finish();
        reject(new HashAbortedError());
      } else {
        finish();
        reject(new Error(msg.message));
      }
    };
    worker.onerror = (e) => {
      finish();
      reject(new Error(e.message));
    };
    worker.postMessage({ type: "hash", file, partSize });
  });

/** Same algorithm on the calling thread (tests, browsers without module workers). */
export const inlineHasher: Hasher = (file, partSize, onProgress, signal) =>
  hashFile(file, partSize, onProgress, () => signal.aborted);

export function defaultHasher(): Hasher {
  return typeof Worker === "function" ? workerHasher : inlineHasher;
}
