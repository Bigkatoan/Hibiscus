"""Resumable chunked upload (operationIds initUpload, getUpload, uploadPart, completeUpload).

Flow (ADR-0010, CONTRACT_NOTES D1):

1. Hash the source once (whole sha256 + per-part sha256). Hashes are cached in the resume state
   file keyed by a stat fingerprint, so an interrupted push does not re-hash on restart.
2. ``POST /uploads`` with a persisted ``Idempotency-Key`` (safe to retry). If the state file has
   an ``upload_id`` that is still ``active`` it is reused instead; the server also returns an
   existing active session for the same (workspace, sha256, size) with 200.
3. ``GET /uploads/{id}`` -> the parts the server already holds (with their sha256). Only missing
   parts, or parts whose stored sha256 differs from ours, are sent.
4. ``PUT /uploads/{id}/parts/{n}`` (≤ 64 MiB, ``X-Content-SHA256``), bounded parallelism,
   retries with exponential backoff (1, 2, 4 … 60 s) on network errors / 5xx / 429.
5. ``POST /uploads/{id}/complete``; ``409 upload_incomplete`` re-sends ``missing_parts`` once.

The state file (``<state_dir>/uploads/<key>.json``) is deleted after a successful complete.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
from collections.abc import Callable
from concurrent.futures import FIRST_EXCEPTION, Future, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from hibiscus.api import ApiError, HibiscusApi, is_transport_error
from hibiscus.archive import FileSource, Source, SourceChangedError, VirtualTar, hash_source, iter_ranges
from hibiscus.config import read_json, state_dir, write_private

MIB = 1024 * 1024
MAX_PART = 64 * MIB  # Cloudflare 100 MB body limit (ADR-0010)
MIN_PART = 5 * MIB
STATE_VERSION = 1


class UploadError(Exception):
    pass


@dataclass
class UploadState:
    version: int
    server: str
    workspace_id: str
    source_path: str
    source_kind: str  # file | dir
    filename: str
    archive_format: str
    fingerprint: str
    size: int
    part_size: int
    sha256: str
    part_sha256: list[str]
    idempotency_key: str
    dataset_id: str | None = None
    new_dataset_name: str | None = None
    upload_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def key(server: str, workspace_id: str, source_path: str) -> str:
        return hashlib.sha256(f"{server}\0{workspace_id}\0{source_path}".encode()).hexdigest()[:32]

    @staticmethod
    def path_for(key: str) -> Path:
        return state_dir() / "uploads" / f"{key}.json"

    @classmethod
    def load(cls, key: str) -> UploadState | None:
        try:
            data = read_json(cls.path_for(key))
        except (ValueError, json.JSONDecodeError):
            return None
        if not data or data.get("version") != STATE_VERSION:
            return None
        try:
            return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        except TypeError:
            return None

    def save(self, key: str) -> None:
        write_private(self.path_for(key), json.dumps(asdict(self), indent=2) + "\n")

    @classmethod
    def delete(cls, key: str) -> None:
        cls.path_for(key).unlink(missing_ok=True)


@dataclass
class UploadEvents:
    """Progress callbacks (the CLI wires these to a rich progress bar)."""

    on_hash_start: Callable[[int], None] = lambda total: None
    on_hash_progress: Callable[[int], None] = lambda n: None
    on_upload_start: Callable[[int, int], None] = lambda total, already: None
    on_part_done: Callable[[int, int], None] = lambda part, nbytes: None
    on_retry: Callable[[int, int, BaseException, float], None] = lambda part, attempt, exc, delay: None
    on_info: Callable[[str], None] = lambda msg: None


@dataclass
class UploadResult:
    upload_id: str
    dataset_id: str
    dataset_name: str
    version_id: str
    version: int
    job_id: str
    resumed_parts: int
    sent_parts: int
    sha256: str
    size: int


def _clamp_part_size(part_size: int) -> int:
    return max(MIN_PART, min(MAX_PART, part_size))


class Uploader:
    def __init__(
        self,
        api: HibiscusApi,
        *,
        parallel: int = 2,
        events: UploadEvents | None = None,
        max_attempts: int | None = None,
    ) -> None:
        self.api = api
        self.parallel = max(1, min(8, parallel))
        self.events = events or UploadEvents()
        self.max_attempts = max_attempts or api.backoff.attempts
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ public
    def push(
        self,
        src: FileSource | VirtualTar,
        *,
        dataset_id: str | None = None,
        new_dataset_name: str | None = None,
        part_size: int = MAX_PART,
    ) -> UploadResult:
        if (dataset_id is None) == (new_dataset_name is None):
            raise ValueError("exactly one of dataset_id / new_dataset_name is required")
        if src.size <= 0:
            raise UploadError("nothing to upload (empty source)")
        workspace_id = str(self.api.ws())
        source_path = str(src.root if isinstance(src, VirtualTar) else src.path)
        key = UploadState.key(self.api.base_url, workspace_id, source_path)
        part_size = _clamp_part_size(part_size)

        state = UploadState.load(key)
        fp = src.fingerprint()
        if state is not None and (
            state.fingerprint != fp
            or state.size != src.size
            or state.dataset_id != dataset_id
            or state.new_dataset_name != new_dataset_name
        ):
            self.events.on_info("source or target changed since the last attempt; starting over")
            state = None

        if state is None:
            state = self._new_state(
                src, fp, workspace_id, source_path, part_size, dataset_id, new_dataset_name
            )
            state.save(key)
        else:
            self.events.on_info("resuming previous upload")

        session = self._ensure_session(state, key, src)
        if session["part_size"] != state.part_size:
            # server clamped the part size: re-hash per-part with the server's layout
            state.part_size = int(session["part_size"])
            state.sha256, state.part_sha256 = self._hash(src, state.part_size)
            state.save(key)

        if session["status"] == "completed":
            return self._finish(
                state, key, src, already_completed=True, resumed=len(state.part_sha256), sent=0
            )

        have = {int(p["part_number"]): str(p["sha256"]) for p in session.get("parts", [])}
        todo: list[tuple[int, int, int]] = []
        already = 0
        for n, off, length in iter_ranges(state.size, state.part_size):
            if have.get(n) == state.part_sha256[n - 1]:
                already += length
            else:
                todo.append((n, off, length))
        resumed = len(state.part_sha256) - len(todo)
        self.events.on_upload_start(state.size, already)
        if state.upload_id is None:  # pragma: no cover - _ensure_session always sets it
            raise UploadError("no upload session")
        self._send_parts(state.upload_id, src, state, todo)
        return self._finish(state, key, src, already_completed=False, resumed=resumed, sent=len(todo))

    # ------------------------------------------------------------------ steps
    def _hash(self, src: Source, part_size: int) -> tuple[str, list[str]]:
        self.events.on_hash_start(src.size)
        return hash_source(src, part_size, self.events.on_hash_progress)

    def _new_state(
        self,
        src: FileSource | VirtualTar,
        fp: str,
        workspace_id: str,
        source_path: str,
        part_size: int,
        dataset_id: str | None,
        new_dataset_name: str | None,
    ) -> UploadState:
        whole, parts = self._hash(src, part_size)
        return UploadState(
            version=STATE_VERSION,
            server=self.api.base_url,
            workspace_id=workspace_id,
            source_path=source_path,
            source_kind="dir" if isinstance(src, VirtualTar) else "file",
            filename=src.name,
            archive_format=src.archive_format,
            fingerprint=fp,
            size=src.size,
            part_size=part_size,
            sha256=whole,
            part_sha256=parts,
            idempotency_key=f"push-{secrets.token_hex(16)}",
            dataset_id=dataset_id,
            new_dataset_name=new_dataset_name,
        )

    def _init_body(self, state: UploadState) -> dict[str, Any]:
        body: dict[str, Any] = {
            "workspace_id": state.workspace_id,
            "filename": state.filename[:255],
            "size": state.size,
            "sha256": state.sha256,
            "archive_format": state.archive_format,
            "part_size": state.part_size,
        }
        if state.dataset_id:
            body["dataset_id"] = state.dataset_id
        else:
            body["new_dataset_name"] = state.new_dataset_name
        return body

    def _ensure_session(self, state: UploadState, key: str, src: Source) -> dict[str, Any]:
        if state.upload_id:
            try:
                sess = self.api.get_upload(state.upload_id).to_dict()
                if sess["status"] in ("active", "completing", "completed") and sess["sha256"] == state.sha256:
                    return sess
                self.events.on_info(f"previous upload session is {sess['status']}; creating a new one")
            except ApiError as exc:
                if exc.status != 404:
                    raise
                self.events.on_info("previous upload session not found; creating a new one")
            state.upload_id = None
            state.idempotency_key = f"push-{secrets.token_hex(16)}"
            state.save(key)
        sess = self.api.init_upload(self._init_body(state), state.idempotency_key).to_dict()
        if sess["sha256"] != state.sha256 or int(sess["size"]) != state.size:
            raise UploadError("server returned a session for a different file (sha256/size mismatch)")
        state.upload_id = str(sess["id"])
        state.save(key)
        return sess

    def _send_parts(
        self, upload_id: str, src: Source, state: UploadState, todo: list[tuple[int, int, int]]
    ) -> None:
        if not todo:
            return
        if self.parallel == 1:
            for n, off, length in todo:
                self._send_one(upload_id, src, state, n, off, length)
            return
        with ThreadPoolExecutor(max_workers=self.parallel, thread_name_prefix="hibiscus-part") as pool:
            futures: list[Future[None]] = [
                pool.submit(self._send_one, upload_id, src, state, n, off, length) for n, off, length in todo
            ]
            done, pending = wait(futures, return_when=FIRST_EXCEPTION)
            for f in pending:
                f.cancel()
            for f in done:
                exc = f.exception()
                if exc is not None:
                    raise exc

    def _send_one(
        self, upload_id: str, src: Source, state: UploadState, n: int, off: int, length: int
    ) -> None:
        expected = state.part_sha256[n - 1]
        checksum_retry_used = False
        attempt = 0
        while True:
            data = src.read(off, length)
            digest = hashlib.sha256(data).hexdigest()
            if digest != expected:
                raise SourceChangedError(f"part {n} content changed since hashing; re-run `hibiscus push`")
            try:
                body = self.api.upload_part(upload_id, n, data, digest)
                if body.get("sha256") != digest or int(body.get("size", -1)) != length:
                    raise UploadError(f"server acknowledged part {n} with a different size/sha256")
                with self._lock:
                    self.events.on_part_done(n, length)
                return
            except ApiError as exc:
                if exc.code == "upload_part_checksum_mismatch" and not checksum_retry_used:
                    checksum_retry_used = True  # corrupted in transit: resend once immediately
                    continue
                if not exc.retryable or attempt + 1 >= self.max_attempts:
                    raise
                delay = self.api.backoff.delay(attempt, exc.retry_after_s)
                self.events.on_retry(n, attempt + 1, exc, delay)
                self.api.backoff.sleep(delay)
                attempt += 1
            except Exception as exc:
                if not is_transport_error(exc) or attempt + 1 >= self.max_attempts:
                    raise
                delay = self.api.backoff.delay(attempt)
                self.events.on_retry(n, attempt + 1, exc, delay)
                self.api.backoff.sleep(delay)
                attempt += 1

    def _finish(
        self, state: UploadState, key: str, src: Source, *, already_completed: bool, resumed: int, sent: int
    ) -> UploadResult:
        if state.upload_id is None:  # pragma: no cover - _ensure_session always sets it
            raise UploadError("no upload session")
        if isinstance(src, (FileSource, VirtualTar)):
            src.check_unchanged()
        try:
            done = self.api.complete_upload(state.upload_id)
        except ApiError as exc:
            if exc.code != "upload_incomplete" or not exc.missing_parts or already_completed:
                raise
            self.events.on_info(f"server is missing parts {exc.missing_parts}; re-sending")
            ranges = {n: (n, off, ln) for n, off, ln in iter_ranges(state.size, state.part_size)}
            todo = [ranges[n] for n in exc.missing_parts if n in ranges]
            self._send_parts(state.upload_id, src, state, todo)
            sent += len(todo)
            done = self.api.complete_upload(state.upload_id)
        d = done.to_dict()
        UploadState.delete(key)
        return UploadResult(
            upload_id=state.upload_id,
            dataset_id=str(d["dataset"]["id"]),
            dataset_name=str(d["dataset"]["name"]),
            version_id=str(d["version"]["id"]),
            version=int(d["version"]["version"]),
            job_id=str(d["job"]["id"]),
            resumed_parts=resumed,
            sent_parts=sent,
            sha256=state.sha256,
            size=state.size,
        )
