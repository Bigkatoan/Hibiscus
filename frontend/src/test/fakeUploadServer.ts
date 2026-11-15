/**
 * Stateful in-memory implementation of the upload endpoints (initUpload, uploadPart, getUpload,
 * completeUpload, abortUpload) used to exercise the real ChunkedUploader end-to-end.
 * It verifies X-Content-SHA256 against the received bytes and the whole-file digest on complete.
 */
import { createHash } from "node:crypto";
import { HttpResponse } from "msw";
import type { Schemas } from "@/api/client";
import * as f from "./fixtures";
import { http, problemResponse } from "./server";

type S = Schemas;

export interface FakeUploadOptions {
  partSize: number;
  /** Return 503 for the first N attempts of these part numbers. */
  flaky?: Record<number, number>;
  /** Corrupt the first upload of these parts (server reports checksum mismatch). */
  corruptOnce?: number[];
  /** Pre-existing session parts (resume). */
  existingParts?: number[];
  /** On the first complete, pretend these parts are missing. */
  missingOnComplete?: number[];
}

export function fakeUploadServer(file: Uint8Array, opts: FakeUploadOptions) {
  const store = new Map<number, Uint8Array>();
  const attempts = new Map<number, number>();
  const corrupted = new Set<number>();
  let session: S["UploadSession"] | null = null;
  let completes = 0;
  const log: string[] = [];
  const sha = (b: Uint8Array) => createHash("sha256").update(b).digest("hex");

  const partsOf = (): S["UploadPart"][] =>
    [...store.entries()]
      .sort(([a], [b]) => a - b)
      .map(([n, b]) => ({ part_number: n, size: b.length, sha256: sha(b) }));

  if (opts.existingParts?.length) {
    for (const n of opts.existingParts) {
      const start = (n - 1) * opts.partSize;
      store.set(n, file.slice(start, Math.min(file.length, start + opts.partSize)));
    }
  }

  const handlers = [
    http.post("/uploads", async ({ request }) => {
      const body = await request.json();
      log.push(`init:${request.headers.get("Idempotency-Key") ? "idem" : "no-idem"}`);
      const resumed = session !== null || (opts.existingParts?.length ?? 0) > 0;
      session = {
        ...f.uploadSession,
        workspace_id: body.workspace_id,
        filename: body.filename,
        size: body.size,
        sha256: body.sha256,
        archive_format: body.archive_format ?? "zip",
        new_dataset_name: body.new_dataset_name ?? null,
        dataset_id: body.dataset_id ?? null,
        part_size: opts.partSize,
        part_count: Math.max(1, Math.ceil(body.size / opts.partSize)),
        parts: partsOf(),
      };
      return HttpResponse.json(session, { status: resumed ? 200 : 201 });
    }),
    http.put("/uploads/{upload_id}/parts/{part_number}", async ({ request, params }) => {
      const n = Number(params.part_number);
      const a = (attempts.get(n) ?? 0) + 1;
      attempts.set(n, a);
      log.push(`put:${n}`);
      if ((opts.flaky?.[n] ?? 0) >= a) return problemResponse(503, "service_unavailable");
      const csrf = request.headers.get("X-CSRF-Token");
      if (csrf) log.push(`csrf:${n}`);
      const buf = new Uint8Array(await request.arrayBuffer());
      const claimed = request.headers.get("X-Content-SHA256");
      let actual = sha(buf);
      if (opts.corruptOnce?.includes(n) && !corrupted.has(n)) {
        corrupted.add(n);
        actual = "0".repeat(64);
      }
      if (claimed !== actual) return problemResponse(422, "upload_part_checksum_mismatch");
      store.set(n, buf);
      return HttpResponse.json({ part_number: n, size: buf.length, sha256: actual, received_at: f.T0 });
    }),
    http.get("/uploads/{upload_id}", () => {
      if (!session) return problemResponse(404, "not_found");
      return HttpResponse.json({ ...session, parts: partsOf() });
    }),
    http.post("/uploads/{upload_id}/complete", () => {
      completes += 1;
      log.push("complete");
      if (!session) return problemResponse(404, "not_found");
      if (completes === 1 && opts.missingOnComplete?.length) {
        for (const n of opts.missingOnComplete) store.delete(n);
        return problemResponse(409, "upload_incomplete", { missing_parts: opts.missingOnComplete });
      }
      const all = new Uint8Array(file.length);
      let off = 0;
      for (const [, b] of [...store.entries()].sort(([x], [y]) => x - y)) {
        all.set(b, off);
        off += b.length;
      }
      if (off !== session.size || sha(all) !== session.sha256)
        return problemResponse(409, "upload_incomplete");
      const result: S["UploadCompleted"] = {
        upload: { ...session, status: "completed", parts: partsOf() },
        dataset: f.dataset,
        version: { ...f.versionSummary, status: "pending" },
        job: f.job,
      };
      return HttpResponse.json(result, { status: 202 });
    }),
    http.delete("/uploads/{upload_id}", ({ response }) => {
      log.push("abort");
      return response(204).empty();
    }),
  ];

  return { handlers, store, log, attempts, getCompletes: () => completes };
}
