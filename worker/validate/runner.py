"""CPU worker loop: claims ``validate_dataset`` / ``import_hf_dataset`` / ``merge_datasets`` jobs.

Protocol (run-lifecycle.md 7.2/7.3): claim with ``FOR UPDATE SKIP LOCKED``, lease 60 s renewed every
10 s by a heartbeat thread; a failed heartbeat (lease lost or job cancelled) aborts the work at
the next progress tick. Infra errors are retried once (``max_attempts = 2``).
"""

from __future__ import annotations

import base64
import json
import logging
import re
import shutil
import sys
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core import metrics
from core.liveness import touch
from validate import db as dbm
from validate.archive import UnpackLimits
from validate.lerobot_tools import merge_datasets
from validate.pipeline import STAGE_WEIGHTS, PipelineInput, PipelineOutput, run_pipeline
from validate.report import StepId
from validate.settings import WorkerSettings
from validate.store import Store, dataset_prefix, derived_prefix

log = logging.getLogger("hibiscus.validate")

HF_URI_RE = re.compile(
    r"^hf://(?P<org>[A-Za-z0-9][A-Za-z0-9_.-]{0,95})/(?P<name>[A-Za-z0-9][A-Za-z0-9_.-]{0,95})(?:@(?P<rev>[A-Za-z0-9_./-]{1,128}))?$"
)
_STAGE_ORDER = list(STAGE_WEIGHTS)


class CancelledError(Exception):
    pass


class JobError(Exception):
    """A non-retryable job failure with a stable ``error_code``."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def parse_hf_uri(uri: str) -> tuple[str, str | None]:
    m = HF_URI_RE.match(uri)
    if m is None or ".." in uri:
        raise JobError("hf_uri_invalid", f"invalid hf uri {uri!r}")
    return f"{m['org']}/{m['name']}", m["rev"]


def decrypt_secret(data_key_b64: str, blob: bytes) -> str:
    """AES-256-GCM ``nonce(12) || ciphertext || tag`` (docs/db-schema.md, secrets at rest)."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = base64.b64decode(data_key_b64)
    plain: bytes = AESGCM(key).decrypt(blob[:12], blob[12:], None)
    return plain.decode()


@dataclass(slots=True)
class _Tracker:
    """Shared between the job thread and the heartbeat thread."""

    progress: float = 0.0
    stage: str = "validate.queued"
    alive: bool = True
    cancelled: bool = False
    stop: threading.Event = field(default_factory=threading.Event)


class Runner:
    def __init__(
        self, settings: WorkerSettings, db: dbm.Db, store: Store, redis_client: Any | None = None
    ) -> None:
        self.s = settings
        self.db = db
        self.store = store
        self.redis = redis_client

    # ---- loop --------------------------------------------------------------------------------
    def run_forever(self, stop: threading.Event) -> None:
        log.info("validate worker started", extra={"worker_id": self.s.worker_id})
        while not stop.is_set():
            touch(self.s.heartbeat_file)  # QC-e2e-08: liveness for the image HEALTHCHECK
            try:
                busy = self.run_once()
            except Exception:  # DB down etc.; never kill the loop
                log.exception("worker loop error")
                busy = False
            if not busy:
                stop.wait(self.s.poll_interval_s)

    def run_once(self) -> bool:
        job = self.db.claim()
        if job is None:
            return False
        self.process(job)
        return True

    # ---- one job -----------------------------------------------------------------------------
    def _finish(self, job: dbm.JobRow, status: str, *args: Any) -> None:
        self.db.finish(job.id, status, *args)
        metrics.job_ended(job.kind, status)

    def process(self, job: dbm.JobRow) -> None:
        metrics.job_claimed(job.kind)
        tracker = _Tracker()
        hb = threading.Thread(target=self._heartbeat, args=(job, tracker), daemon=True)
        hb.start()
        work = self.s.work_dir / str(job.id)
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True)
        if job.kind == "push_model_hub":
            try:
                self._push_hub(job, work, tracker)
            finally:
                tracker.stop.set()
                hb.join(timeout=5)
                shutil.rmtree(work, ignore_errors=True)
            return
        version_id = job.dataset_version_id or _uuid(job.payload.get("dataset_version_id"))
        try:
            if version_id is None:
                raise JobError("bad_request", "job has no dataset_version_id")
            version = self.db.get_version(version_id)
            if version is None:
                raise JobError("not_found", "dataset version not found")
            if job.kind == "validate_dataset":
                result = self._validate(job, version, work, tracker)
            elif job.kind == "import_hf_dataset":
                result = self._import_hf(job, version, work, tracker)
            elif job.kind == "merge_datasets":
                result = self._merge(job, version, work, tracker)
            else:
                raise JobError("bad_request", f"unsupported job kind {job.kind}")
            code = result.pop("error_code", None)
            self._finish(job, "failed" if code else "succeeded", result, code, result.get("message"))
        except CancelledError:
            log.warning("job cancelled or lease lost", extra={"job_id": str(job.id)})
            if version_id is not None:
                self.db.set_version_status(version_id, "failed")
                self._publish(job.workspace_id, version_id, "failed", "cancelled")
            self._finish(job, "cancelled", {"stage": tracker.stage}, "cancelled", None)
        except JobError as exc:
            if version_id is not None:
                self.db.set_version_status(version_id, "failed")
                self._publish(job.workspace_id, version_id, "failed", exc.code)
            self._finish(job, "failed", {"stage": tracker.stage}, exc.code, str(exc)[:2000])
        except Exception as exc:
            log.exception("job crashed", extra={"job_id": str(job.id)})
            msg = f"{type(exc).__name__}: {exc}"[:2000]
            if job.attempts < job.max_attempts:
                if version_id is not None:
                    self.db.set_version_status(version_id, "pending")
                self.db.requeue(job.id, "internal_error", msg)
            else:
                if version_id is not None:
                    self.db.set_version_status(version_id, "failed")
                    self._publish(job.workspace_id, version_id, "failed", "internal_error")
                self._finish(job, "failed", {"stage": tracker.stage}, "internal_error", msg)
        finally:
            tracker.stop.set()
            hb.join(timeout=5)
            shutil.rmtree(work, ignore_errors=True)

    def _heartbeat(self, job: dbm.JobRow, t: _Tracker) -> None:
        while not t.stop.wait(self.s.heartbeat_s):
            try:
                if not self.db.heartbeat(job.id, t.progress, t.stage):
                    metrics.lease_heartbeat(False)
                    t.cancelled = True
                    return
                metrics.lease_heartbeat(True)
                touch(self.s.heartbeat_file)  # QC-e2e-08: a busy worker stays healthy
            except Exception:
                log.exception("heartbeat failed")

    # ---- storage quota (SEC-input-3) ---------------------------------------------------------
    def _remaining(self, job: dbm.JobRow, v: dbm.VersionRow) -> int:
        remaining = self.db.storage_remaining(v.workspace_id, job.created_by, v.id)
        if remaining <= 0:
            raise JobError("quota_exceeded", "workspace storage quota exceeded")
        return remaining

    def _limits(self, job: dbm.JobRow, v: dbm.VersionRow) -> UnpackLimits:
        """Archive expansion may not exceed the workspace's remaining storage."""
        lim = self.s.limits
        return replace(lim, max_total_bytes=min(lim.max_total_bytes, self._remaining(job, v)))

    # ---- push to the Hub (QC-backend-02) -------------------------------------------------------
    def _push_hub(self, job: dbm.JobRow, work: Path, t: _Tracker) -> None:
        from validate import hub_push as hp

        try:
            req = hp.PushRequest.from_payload(job.payload)
            model_id = job.model_id or _uuid(job.payload.get("model_id"))
            model = self.db.get_model(model_id) if model_id else None
            if model is None or model.get("deleted_at") is not None or model.get("status") != "ready":
                raise hp.HubPushError("model_not_ready", "model is not ready")
            uri = str(model.get("bundle_uri") or "")
            if not uri.startswith("s3://"):
                raise hp.HubPushError("model_not_ready", "model has no bundle")
            token = self._hf_token(job.created_by)
            if not token:
                raise hp.HubPushError("hf_token_missing", "no usable Hugging Face token stored")
            bucket, _, key = uri[len("s3://") :].partition("/")
            t.stage = "push.download"
            zip_path = work / "bundle.zip"
            self.store.download(bucket, key, zip_path)
            if t.cancelled:
                raise CancelledError
            t.progress = 0.3
            bundle_dir = hp.extract_bundle(zip_path, work / "unzipped")
            folder = hp.stage_repo(
                bundle_dir,
                work / "repo",
                include_onnx=req.include_onnx,
                policy_type=str(model.get("policy_type")),
                dataset=None,
            )
            t.stage = "push.upload"
            t.progress = 0.5
            commit = hp.push(folder, req, token=token, commit_message=f"Hibiscus: {model.get('name')}")
            if t.cancelled:
                raise CancelledError
            self.db.mark_pushed(model["id"], req.repo_id)
            self._finish(job, "succeeded", {"repo_id": req.repo_id, "commit": commit, "stage": "push.done"})
        except CancelledError:
            self._finish(job, "cancelled", {"stage": t.stage}, "cancelled", None)
        except hp.HubPushError as exc:
            self._finish(job, "failed", {"stage": t.stage}, exc.code, str(exc)[:2000])
        except Exception as exc:
            log.exception("hub push crashed", extra={"job_id": str(job.id)})
            msg = f"{type(exc).__name__}: {exc}"[:2000]
            if job.attempts < job.max_attempts:
                self.db.requeue(job.id, "internal_error", msg)
            else:
                self._finish(job, "failed", {"stage": t.stage}, "internal_error", msg)

    def _progress_fn(
        self, job: dbm.JobRow, version: dbm.VersionRow, t: _Tracker, base: float, span: float
    ) -> Callable[[StepId | str, float], None]:
        state = {"validating": False}

        def cb(stage: StepId | str, frac: float) -> None:
            if t.cancelled:
                raise CancelledError
            name = str(stage)
            idx = _STAGE_ORDER.index(name) if name in _STAGE_ORDER else 0
            done = sum(STAGE_WEIGHTS[s] for s in _STAGE_ORDER[:idx]) + STAGE_WEIGHTS.get(name, 0.0) * frac
            t.progress = base + span * min(done, 1.0)
            t.stage = f"validate.{name}"
            if name not in ("checksum", "unpack") and not state["validating"]:
                state["validating"] = True
                self.db.set_version_status(version.id, "validating")
                self._publish(job.workspace_id, version.id, "validating", None)

        return cb

    # ---- validate ----------------------------------------------------------------------------
    def _validate(self, job: dbm.JobRow, v: dbm.VersionRow, work: Path, t: _Tracker) -> dict[str, Any]:
        manifest_key = derived_prefix(str(v.workspace_id), str(v.dataset_id), str(v.id)) + "manifest.json"
        use_stored = bool(v.storage_prefix) and self.store.exists(self.s.bucket_datasets, manifest_key)
        if use_stored:
            ds_dir = work / "stored"
            self._download_stored(v, ds_dir / (v.dataset_slug or "dataset"))
            inp = PipelineInput(
                str(v.id), work / "pipe", job_id=str(job.id), dataset_dir=ds_dir, limits=self.s.limits
            )
            self.db.set_version_status(v.id, "validating")
        else:
            upload = self.db.get_upload_for_version(v.id)
            if upload is None:
                raise JobError("upload_missing", "no upload object for this version")
            self.db.set_version_status(v.id, "unpacking")
            self._publish(job.workspace_id, v.id, "unpacking", None)
            t.stage = "validate.download"
            archive = work / "upload.bin"
            self.store.download(upload.s3_bucket, upload.s3_key, archive)
            inp = PipelineInput(
                str(v.id),
                work / "pipe",
                job_id=str(job.id),
                archive=archive,
                expected_sha256=upload.sha256,
                limits=self._limits(job, v),
            )
        out = run_pipeline(inp, self._progress_fn(job, v, t, 0.0, 0.95))
        return self._store_outcome(job, v, out, upload_dataset=not use_stored, t=t)

    def _download_stored(self, v: dbm.VersionRow, dest: Path) -> None:
        dprefix = derived_prefix(str(v.workspace_id), str(v.dataset_id), str(v.id))
        manifest = self.store.get_json(self.s.bucket_datasets, dprefix + "manifest.json")
        files = [str(f["path"]) for f in manifest["files"]]
        self.store.download_tree(
            self.s.bucket_datasets,
            dataset_prefix(str(v.workspace_id), str(v.dataset_id), str(v.id)),
            files,
            dest,
        )

    def _store_outcome(
        self, job: dbm.JobRow, v: dbm.VersionRow, out: PipelineOutput, *, upload_dataset: bool, t: _Tracker
    ) -> dict[str, Any]:
        report = dbm.to_json_safe(out.report.to_json())
        summary = report["summary"]
        if out.status == "failed" or out.dataset_root is None or out.content_hash is None:
            status = out.status if out.status == "failed" else "invalid"
            self.db.finalize_version(v.id, status, {"validate_report": report})
            self._publish(job.workspace_id, v.id, status, out.error_code)
            res: dict[str, Any] = {"version_status": status, "summary": summary, "stage": t.stage}
            if out.error_code:
                res["error_code"] = out.error_code
            return res
        if v.content_hash and v.content_hash != out.content_hash:
            raise JobError("content_hash_mismatch", "stored dataset no longer matches its content hash")
        dup = self.db.duplicate_of(v.dataset_id, v.id, out.content_hash)
        if dup is not None:
            self.db.finalize_version(v.id, "failed", {"validate_report": report})
            self._publish(job.workspace_id, v.id, "failed", "dataset_version_duplicate")
            return {
                "version_status": "failed",
                "summary": summary,
                "duplicate_of": str(dup),
                "error_code": "dataset_version_duplicate",
                "message": f"identical content already exists as version {dup}",
                "stage": t.stage,
            }
        ws, ds, vid = str(v.workspace_id), str(v.dataset_id), str(v.id)
        bucket = self.s.bucket_datasets
        t.stage = "validate.store"
        if upload_dataset and (out.size_bytes or 0) > self._remaining(job, v):
            # SEC-input-3: re-checked right before storing (HF import, merge, archive expansion)
            raise JobError(
                "quota_exceeded",
                f"dataset is {out.size_bytes} bytes; it does not fit in the workspace storage quota",
            )
        if upload_dataset:
            self.store.upload_tree(out.dataset_root, bucket, dataset_prefix(ws, ds, vid), out.files)
        dpre = derived_prefix(ws, ds, vid)
        self.store.delete_prefix(bucket, dpre)
        if out.derived_dir is not None and out.derived_dir.is_dir():
            self.store.upload_tree(out.derived_dir, bucket, dpre)
        self.store.put_json(
            bucket,
            dpre + "manifest.json",
            {
                "dataset_version_id": vid,
                "content_hash": out.content_hash,
                "size_bytes": out.size_bytes,
                "files": [{"path": f.path, "size": f.size, "sha256": f.sha256} for f in out.files],
            },
        )
        f = out.fields
        fields: dict[str, Any] = {
            "content_hash": out.content_hash,
            "storage_prefix": f"s3://{bucket}/{dataset_prefix(ws, ds, vid)}",
            "size_bytes": out.size_bytes,
            "codebase_version": f.get("codebase_version"),
            "robot_type": (str(f["robot_type"])[:64] if f.get("robot_type") else None),
            "fps": f.get("fps"),
            "total_episodes": f.get("total_episodes"),
            "total_frames": f.get("total_frames"),
            "camera_keys": f.get("camera_keys"),
            "features": dbm.to_json_safe(f.get("features")),
            "info": dbm.to_json_safe(f.get("info")),
            "stats": dbm.to_json_safe(f.get("stats")),
            "validate_report": report,
            "preview": dbm.to_json_safe(out.preview) if out.preview is not None else None,
        }
        if f.get("converted_from"):
            fields["converted_from"] = f["converted_from"]
        self.db.finalize_version(v.id, out.status, fields)
        self._publish(job.workspace_id, v.id, out.status, None)
        return {
            "version_status": out.status,
            "summary": summary,
            "content_hash": out.content_hash,
            "size_bytes": out.size_bytes,
            "stage": "validate.done",
        }

    # ---- HF import ---------------------------------------------------------------------------
    def _import_hf(self, job: dbm.JobRow, v: dbm.VersionRow, work: Path, t: _Tracker) -> dict[str, Any]:
        uri = str(job.payload.get("hf_uri") or v.source_ref or "")
        repo_id, revision = parse_hf_uri(uri)
        token = self._hf_token(job.created_by)
        t.stage = "import.download"
        self.db.set_version_status(v.id, "unpacking")
        self._publish(job.workspace_id, v.id, "unpacking", None)
        dest = work / "hf" / repo_id.split("/", 1)[1]
        try:
            from huggingface_hub import snapshot_download
            from huggingface_hub.errors import HfHubHTTPError, RepositoryNotFoundError, RevisionNotFoundError

            # SEC-input-3: size the repo before downloading anything.
            cap = min(self.s.hf_import_max_bytes, self._remaining(job, v))
            total = self._hf_repo_bytes(repo_id, revision, token)
            if total > cap:
                raise JobError(
                    "quota_exceeded",
                    f"{repo_id} is {total} bytes; the limit for this import is {cap} bytes "
                    "(workspace storage quota / import cap)",
                )
            snapshot_download(
                repo_id,
                repo_type="dataset",
                revision=revision,
                local_dir=str(dest),
                token=token,
                cache_dir=str(self.s.hf_home / "hub"),
            )
        except (RepositoryNotFoundError, RevisionNotFoundError) as exc:
            raise JobError(
                "hf_not_found", f"{repo_id}@{revision or 'main'} not found or not accessible"
            ) from exc
        except HfHubHTTPError as exc:
            raise RuntimeError(f"hub download failed: {exc}") from exc
        shutil.rmtree(dest / ".cache", ignore_errors=True)
        got = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file() and not f.is_symlink())
        if got > cap:  # the listing lied or the repo changed between listing and download
            raise JobError("quota_exceeded", f"{repo_id}: downloaded {got} bytes, above the {cap} byte limit")
        t.progress = 0.3
        inp = PipelineInput(
            str(v.id), work / "pipe", job_id=str(job.id), dataset_dir=dest.parent, limits=self.s.limits
        )
        out = run_pipeline(inp, self._progress_fn(job, v, t, 0.3, 0.65))
        return self._store_outcome(job, v, out, upload_dataset=True, t=t)

    def _hf_repo_bytes(self, repo_id: str, revision: str | None, token: str | None) -> int:
        """Total size of the dataset repo's files (``dataset_info(files_metadata=True)``)."""
        from huggingface_hub import HfApi

        info = HfApi().dataset_info(repo_id, revision=revision, files_metadata=True, token=token)
        return sum(int(s.size or 0) for s in (info.siblings or []))

    def _hf_token(self, user_id: uuid.UUID | None) -> str | None:
        if user_id is None or not self.s.data_key_b64:
            return None
        from sqlalchemy import text

        with self.db.engine.begin() as c:
            row = c.execute(
                text("SELECT ciphertext FROM user_secrets WHERE user_id = :u AND kind = 'hf_token'"),
                {"u": user_id},
            ).first()
        if row is None:
            return None
        try:
            return decrypt_secret(self.s.data_key_b64, bytes(row[0]))
        except Exception:  # wrong key / format: fall back to anonymous access
            log.warning("cannot decrypt hf token; importing anonymously")
            return None

    # ---- merge -------------------------------------------------------------------------------
    def _merge(self, job: dbm.JobRow, v: dbm.VersionRow, work: Path, t: _Tracker) -> dict[str, Any]:
        parsed = [_uuid(x) for x in job.payload.get("source_version_ids", [])]
        src_ids = [x for x in parsed if x is not None] or list(v.merged_from or [])
        if len(src_ids) < 2 or len(src_ids) != max(len(parsed), len(src_ids)):
            raise JobError("bad_request", "merge needs at least two valid source versions")
        roots: list[Path] = []
        t.stage = "merge.download"
        self.db.set_version_status(v.id, "unpacking")
        for i, sid in enumerate(src_ids):
            src = self.db.get_version(sid)
            if src is None or src.status != "ready" or not src.storage_prefix:
                raise JobError("dataset_version_not_ready", f"source version {sid} is not ready")
            dest = work / "sources" / f"src{i}"
            self._download_stored(src, dest)
            roots.append(dest)
        t.stage = "merge.aggregate"
        t.progress = 0.2
        merged_parent = work / "merged"
        res = merge_datasets(roots, merged_parent / (v.dataset_slug or "merged"))
        if not res.ok:
            raise JobError("merge_failed", res.message)
        t.progress = 0.35
        inp = PipelineInput(
            str(v.id), work / "pipe", job_id=str(job.id), dataset_dir=merged_parent, limits=self.s.limits
        )
        out = run_pipeline(inp, self._progress_fn(job, v, t, 0.35, 0.6))
        return self._store_outcome(job, v, out, upload_dataset=True, t=t)

    # ---- events ------------------------------------------------------------------------------
    def _publish(
        self, workspace_id: uuid.UUID, version_id: uuid.UUID, status: str, error_code: str | None
    ) -> None:
        if self.redis is None:
            return
        payload = {
            "event": "dataset_version.status",
            "data": {
                "resource": "dataset_version",
                "id": str(version_id),
                "status": status,
                "error_code": error_code,
                "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            },
        }
        try:
            self.redis.publish(f"hibiscus:ws:{workspace_id}", json.dumps(payload))
        except Exception:
            log.warning("redis publish failed")


def _uuid(v: Any) -> uuid.UUID | None:
    if v is None:
        return None
    try:
        return v if isinstance(v, uuid.UUID) else uuid.UUID(str(v))
    except ValueError:
        return None


def main() -> None:  # pragma: no cover - process entrypoint, exercised by the container
    import signal

    logging.basicConfig(
        level=logging.INFO, format='{"ts":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}'
    )
    from core.hardening import scrub_secret_env, set_non_dumpable

    set_non_dumpable()  # SEC-input-2: the sandboxed tools cannot read /proc/<ppid>/environ
    settings = WorkerSettings.from_env()
    scrub_secret_env()  # settings are built; nothing re-reads the secrets from the environment
    metrics.set_info("cpu", "none", "validate")
    metrics.start_metrics_server(settings.metrics_port)
    redis_client = None
    if settings.redis_url:
        import redis

        redis_client = redis.Redis.from_url(settings.redis_url)
    runner = Runner(
        settings,
        dbm.Db(dbm.make_engine(settings.database_url), settings.worker_id, settings.lease_s),
        Store(settings.s3_endpoint_url, settings.s3_access_key, settings.s3_secret_key, settings.s3_region),
        redis_client,
    )
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    if "--once" in sys.argv[1:]:
        while runner.run_once():  # drain the queue, then exit (tests / cron)
            pass
        return
    runner.run_forever(stop)
