/**
 * Resumable chunked dataset upload (ADR-0010, OpenAPI initUpload / uploadPart / getUpload /
 * completeUpload / abortUpload).
 *
 * Flow: hash (whole file + per part, Web Worker) -> POST /uploads (server may return an existing
 * active session for the same sha256+size => natural resume) -> PUT missing parts with bounded
 * parallelism, X-Content-SHA256, retry with exponential backoff on network / 5xx / 429 and refresh
 * on 401 token_expired -> POST /complete (re-sends `missing_parts` if the server reports any).
 */
import {
  ApiError,
  apiUrl,
  api,
  CSRF_COOKIE,
  CSRF_HEADER,
  isProblem,
  newIdempotencyKey,
  readCookie,
  refreshSession,
  unwrap,
  type Schemas,
} from "@/api/client";
import { defaultHasher, type Hasher } from "./hasher";
import { hashBlob, MAX_PART_SIZE, partRange, type FileHashes } from "./hashing";
import { prefs } from "@/lib/utils";

type S = Schemas;

export type UploadPhase =
  "idle" | "hashing" | "initializing" | "uploading" | "paused" | "completing" | "done" | "error" | "aborted";

export interface UploadState {
  phase: UploadPhase;
  totalBytes: number;
  hashedBytes: number;
  uploadedBytes: number;
  partsDone: number;
  partCount: number;
  session: S["UploadSession"] | null;
  result: S["UploadCompleted"] | null;
  error: ApiError | null;
  resumed: boolean;
}

export interface PartResponse {
  status: number;
  body: unknown;
}

/** PUT one part. `onProgress(loadedBytes)` for this part. */
export type PartTransport = (
  url: string,
  body: Blob,
  headers: Record<string, string>,
  onProgress: (loaded: number) => void,
  signal: AbortSignal,
) => Promise<PartResponse>;

export class TransportError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "TransportError";
  }
}

class PausedError extends Error {
  constructor() {
    super("paused");
    this.name = "PausedError";
  }
}

export const xhrTransport: PartTransport = (url, body, headers, onProgress, signal) =>
  new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    xhr.withCredentials = true;
    xhr.timeout = 300_000;
    for (const [k, v] of Object.entries(headers)) xhr.setRequestHeader(k, v);
    xhr.upload.onprogress = (e) => {
      onProgress(e.loaded);
    };
    xhr.onload = () => {
      let parsed: unknown = null;
      try {
        parsed = JSON.parse(xhr.responseText);
      } catch {
        parsed = null;
      }
      resolve({ status: xhr.status, body: parsed });
    };
    xhr.onerror = () => {
      reject(new TransportError("network"));
    };
    xhr.ontimeout = () => {
      reject(new TransportError("timeout"));
    };
    xhr.onabort = () => {
      reject(new PausedError());
    };
    signal.addEventListener(
      "abort",
      () => {
        xhr.abort();
      },
      { once: true },
    );
    xhr.send(body);
  });

export const fetchTransport: PartTransport = async (url, body, headers, onProgress, signal) => {
  try {
    const res = await fetch(url, { method: "PUT", body, headers, credentials: "same-origin", signal });
    onProgress(body.size);
    let parsed: unknown = null;
    try {
      parsed = await res.json();
    } catch {
      parsed = null;
    }
    return { status: res.status, body: parsed };
  } catch (e) {
    if (signal.aborted) throw new PausedError();
    throw new TransportError(String(e));
  }
};

export function inferArchiveFormat(filename: string): S["ArchiveFormat"] | null {
  const f = filename.toLowerCase();
  if (f.endsWith(".zip")) return "zip";
  if (f.endsWith(".tar.gz") || f.endsWith(".tgz")) return "tar.gz";
  if (f.endsWith(".tar.zst") || f.endsWith(".tzst")) return "tar.zst";
  if (f.endsWith(".tar")) return "tar";
  if (f.endsWith(".rar")) return "rar";
  return null;
}

export interface UploadTarget {
  workspaceId: string;
  /** Existing dataset => new version; otherwise `newDatasetName` creates the dataset. */
  datasetId?: string;
  newDatasetName?: string;
}

export interface UploaderOptions {
  concurrency?: number;
  maxAttempts?: number;
  hasher?: Hasher;
  transport?: PartTransport;
  sleep?: (ms: number) => Promise<void>;
  /** Cache hashes per (name, size, mtime) so a resumed upload does not re-hash (per-viewer pref). */
  cacheHashes?: boolean;
}

const RETRYABLE_STATUS = new Set([408, 429, 500, 502, 503, 504]);
const defaultSleep = (ms: number) =>
  new Promise<void>((r) => {
    setTimeout(r, ms);
  });

export function retryDelayMs(attempt: number, retryAfterS?: number): number {
  if (retryAfterS !== undefined && retryAfterS > 0) return Math.min(60_000, retryAfterS * 1000);
  return Math.min(60_000, 1000 * 2 ** attempt);
}

function hashCacheKey(file: File | Blob): string | null {
  if (!(file instanceof File)) return null;
  return `upload-hash:${file.name}:${file.size}:${file.lastModified}`;
}

export class ChunkedUploader {
  readonly file: File;
  readonly target: UploadTarget;
  private readonly opts: Required<UploaderOptions>;
  private listeners = new Set<(s: UploadState) => void>();
  private controller = new AbortController();
  private hashes: FileHashes | null = null;
  private partLoaded = new Map<number, number>();
  private doneBytes = 0;
  private readonly idempotencyKey = newIdempotencyKey();
  state: UploadState;

  constructor(file: File, target: UploadTarget, options: UploaderOptions = {}) {
    this.file = file;
    this.target = target;
    this.opts = {
      concurrency: options.concurrency ?? 3,
      maxAttempts: options.maxAttempts ?? 8,
      hasher: options.hasher ?? defaultHasher(),
      transport: options.transport ?? xhrTransport,
      sleep: options.sleep ?? defaultSleep,
      cacheHashes: options.cacheHashes ?? true,
    };
    this.state = {
      phase: "idle",
      totalBytes: file.size,
      hashedBytes: 0,
      uploadedBytes: 0,
      partsDone: 0,
      partCount: 0,
      session: null,
      result: null,
      error: null,
      resumed: false,
    };
  }

  private aborted(): boolean {
    return this.controller.signal.aborted;
  }

  subscribe(listener: (s: UploadState) => void): () => void {
    this.listeners.add(listener);
    listener(this.state);
    return () => this.listeners.delete(listener);
  }

  private set(patch: Partial<UploadState>): void {
    this.state = { ...this.state, ...patch };
    for (const l of this.listeners) l(this.state);
  }

  private emitBytes(): void {
    let inflight = 0;
    for (const v of this.partLoaded.values()) inflight += v;
    this.set({ uploadedBytes: Math.min(this.file.size, this.doneBytes + inflight) });
  }

  /** Runs (or resumes) the upload until completion, pause, abort or a fatal error. */
  async start(): Promise<S["UploadCompleted"] | null> {
    if (this.state.phase === "done") return this.state.result;
    this.controller = new AbortController();
    this.set({ error: null });
    try {
      const hashes = await this.ensureHashes();
      this.set({ phase: "initializing" });
      const session = await this.init(hashes);
      this.set({ session, partCount: session.part_count });
      await this.uploadMissing(session, hashes);
      return await this.complete(session, hashes);
    } catch (e) {
      if (e instanceof PausedError || this.controller.signal.aborted) {
        if (this.state.phase !== "aborted") this.set({ phase: "paused" });
        return null;
      }
      const err = e instanceof ApiError ? e : new ApiError(0, null, "network_error");
      this.set({ phase: "error", error: err });
      return null;
    }
  }

  pause(): void {
    if (this.state.phase === "done" || this.state.phase === "aborted") return;
    this.controller.abort();
    this.set({ phase: "paused" });
  }

  async abort(): Promise<void> {
    this.controller.abort();
    const id = this.state.session?.id;
    this.set({ phase: "aborted" });
    if (id) {
      try {
        await unwrap(api.DELETE("/uploads/{upload_id}", { params: { path: { upload_id: id } } }));
      } catch {
        /* best effort: the janitor aborts stale sessions after 7 days */
      }
    }
  }

  private async ensureHashes(): Promise<FileHashes> {
    if (this.hashes) return this.hashes;
    const key = this.opts.cacheHashes ? hashCacheKey(this.file) : null;
    if (key) {
      const cached = prefs.get(key);
      if (cached) {
        try {
          const parsed = JSON.parse(cached) as FileHashes;
          if (typeof parsed.sha256 === "string" && Array.isArray(parsed.parts)) {
            this.hashes = parsed;
            this.set({ hashedBytes: this.file.size });
            return parsed;
          }
        } catch {
          /* ignore corrupt cache */
        }
      }
    }
    this.set({ phase: "hashing", hashedBytes: 0 });
    const hashes = await this.opts.hasher(
      this.file,
      MAX_PART_SIZE,
      (bytes) => {
        this.set({ hashedBytes: bytes });
      },
      this.controller.signal,
    );
    this.hashes = hashes;
    if (key) prefs.set(key, JSON.stringify(hashes));
    return hashes;
  }

  private async init(hashes: FileHashes): Promise<S["UploadSession"]> {
    const body: S["UploadInit"] = {
      workspace_id: this.target.workspaceId,
      filename: this.file.name,
      size: this.file.size,
      sha256: hashes.sha256,
      part_size: hashes.partSize,
      ...(this.target.datasetId ? { dataset_id: this.target.datasetId } : {}),
      ...(!this.target.datasetId && this.target.newDatasetName
        ? { new_dataset_name: this.target.newDatasetName }
        : {}),
    };
    const fmt = inferArchiveFormat(this.file.name);
    if (fmt) body.archive_format = fmt;
    const res = await api.POST("/uploads", {
      body,
      params: { header: { "Idempotency-Key": this.idempotencyKey } },
    });
    if (!res.response.ok || !res.data) {
      throw new ApiError(res.response.status, isProblem(res.error) ? res.error : null);
    }
    const resumed = res.response.status === 200 && res.data.parts.length > 0;
    this.set({ resumed });
    return res.data;
  }

  private async partHash(n: number, session: S["UploadSession"], hashes: FileHashes): Promise<string> {
    if (session.part_size === hashes.partSize) {
      const h = hashes.parts[n - 1];
      if (h) return h;
    }
    const [start, end] = partRange(n, this.file.size, session.part_size);
    return hashBlob(this.file.slice(start, end));
  }

  private async uploadMissing(
    session: S["UploadSession"],
    hashes: FileHashes,
    only?: number[],
  ): Promise<void> {
    const received = new Map(session.parts.map((p) => [p.part_number, p]));
    const todo: number[] = [];
    let done = 0;
    for (let n = 1; n <= session.part_count; n += 1) {
      const [start, end] = partRange(n, this.file.size, session.part_size);
      let needed: boolean;
      if (only) {
        needed = only.includes(n);
      } else {
        const have = received.get(n);
        needed = !(have?.size === end - start && have.sha256 === (await this.partHash(n, session, hashes)));
      }
      if (needed) todo.push(n);
      else done += end - start;
    }
    this.doneBytes = done;
    this.partLoaded.clear();
    this.set({ phase: "uploading", partsDone: session.part_count - todo.length });
    this.emitBytes();

    const queue = [...todo];
    const workers = Array.from({ length: Math.min(this.opts.concurrency, queue.length) }, async () => {
      for (let n = queue.shift(); n !== undefined; n = queue.shift()) {
        await this.uploadPart(session, hashes, n);
      }
    });
    await Promise.all(workers);
  }

  private async uploadPart(session: S["UploadSession"], hashes: FileHashes, n: number): Promise<void> {
    const [start, end] = partRange(n, this.file.size, session.part_size);
    const blob = this.file.slice(start, end);
    let sha = await this.partHash(n, session, hashes);
    let rehashed = false;
    const url = apiUrl(`/uploads/${session.id}/parts/${n}`);
    for (let attempt = 0; ; attempt += 1) {
      if (this.controller.signal.aborted) throw new PausedError();
      const headers: Record<string, string> = {
        "Content-Type": "application/octet-stream",
        "X-Content-SHA256": sha,
      };
      const csrf = readCookie(CSRF_COOKIE);
      if (csrf) headers[CSRF_HEADER] = csrf;
      let res: PartResponse | null = null;
      try {
        res = await this.opts.transport(
          url,
          blob,
          headers,
          (loaded) => {
            this.partLoaded.set(n, loaded);
            this.emitBytes();
          },
          this.controller.signal,
        );
      } catch (e) {
        if (e instanceof PausedError || this.aborted()) throw new PausedError();
        res = null; // network error -> retry
      }
      this.partLoaded.delete(n);
      if (res && res.status >= 200 && res.status < 300) {
        this.doneBytes += end - start;
        this.set({ partsDone: this.state.partsDone + 1 });
        this.emitBytes();
        return;
      }
      const problem = res && isProblem(res.body) ? res.body : null;
      if (res?.status === 401 && problem?.code === "token_expired") {
        if (await refreshSession()) continue;
        throw new ApiError(401, problem);
      }
      if (res && problem?.code === "upload_part_checksum_mismatch" && !rehashed) {
        // The cached digest may be stale (file changed on disk): re-hash this part once.
        sha = await hashBlob(blob);
        rehashed = true;
        continue;
      }
      const retryable = res === null || RETRYABLE_STATUS.has(res.status);
      if (!retryable || attempt + 1 >= this.opts.maxAttempts) {
        throw res ? new ApiError(res.status, problem) : new ApiError(0, null, "network_error");
      }
      this.emitBytes();
      await this.opts.sleep(retryDelayMs(attempt, problem?.retry_after_s));
    }
  }

  private async complete(session: S["UploadSession"], hashes: FileHashes): Promise<S["UploadCompleted"]> {
    for (let round = 0; round < 3; round += 1) {
      this.set({ phase: "completing" });
      const res = await api.POST("/uploads/{upload_id}/complete", {
        params: { path: { upload_id: session.id } },
      });
      if (res.response.ok && res.data) {
        this.set({ phase: "done", result: res.data, uploadedBytes: this.file.size });
        const key = hashCacheKey(this.file);
        if (key) prefs.set(key, "");
        return res.data;
      }
      const problem = isProblem(res.error) ? res.error : null;
      if (problem?.code === "upload_incomplete" && problem.missing_parts?.length) {
        const fresh = await unwrap(
          api.GET("/uploads/{upload_id}", { params: { path: { upload_id: session.id } } }),
        );
        await this.uploadMissing(fresh, hashes, problem.missing_parts);
        continue;
      }
      throw new ApiError(res.response.status, problem);
    }
    throw new ApiError(409, null);
  }
}
