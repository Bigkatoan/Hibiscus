/// <reference lib="webworker" />
import { hashFile, HashAbortedError } from "./hashing";

interface HashRequest {
  type: "hash";
  file: Blob;
  partSize: number;
}
interface AbortRequest {
  type: "abort";
}

let aborted = false;

self.onmessage = (ev: MessageEvent<HashRequest | AbortRequest>) => {
  const msg = ev.data;
  if (msg.type === "abort") {
    aborted = true;
    return;
  }
  aborted = false;
  let last = 0;
  hashFile(
    msg.file,
    msg.partSize,
    (bytes) => {
      const now = Date.now();
      if (now - last > 100 || bytes === msg.file.size) {
        last = now;
        self.postMessage({ type: "progress", bytes });
      }
    },
    () => aborted,
  )
    .then((result) => {
      self.postMessage({ type: "done", result });
    })
    .catch((e: unknown) => {
      self.postMessage({ type: e instanceof HashAbortedError ? "aborted" : "error", message: String(e) });
    });
};
