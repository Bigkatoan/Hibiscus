"""Checkpoint upload / restore (run-lifecycle §4) - background, sequential, ``is_last`` moves atomically."""

from __future__ import annotations

import logging
import os
import shutil
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.bus import Bus
from core.events import Outbox, append_run_event, iso, utcnow
from core.s3 import ObjectStore, StorageError
from core.tables import checkpoints

log = logging.getLogger(__name__)


class CheckpointCorruptError(RuntimeError):
    """Maps to run error ``checkpoint_corrupt`` (infra)."""


@dataclass(frozen=True, slots=True)
class Uploaded:
    step: int
    checkpoint_id: uuid.UUID
    size_bytes: int


def ckpt_dir(output_dir: Path, step: int) -> Path:
    return output_dir / "checkpoints" / f"{step:06d}"


def is_complete(output_dir: Path, step: int) -> bool:
    """Checkpoint ``step`` is fully written.

    lerobot-train repoints ``checkpoints/last`` only after a checkpoint is complete, so ``last``
    pointing at ``step`` *or a newer step* means ``step`` is done. (Requiring ``last == step`` made
    an upload that started after the next save never see its checkpoint as complete: it waited
    ``checkpoint_complete_timeout_s`` and failed the attempt - seen with fast saves on slow hosts.)
    """
    d = ckpt_dir(output_dir, step)
    last = output_dir / "checkpoints" / "last"
    if not (
        (d / "training_state" / "training_step.json").exists()
        and (d / "pretrained_model" / "config.json").exists()
        and last.is_symlink()
    ):
        return False
    target = os.readlink(last).rstrip("/").rsplit("/", 1)[-1]
    return target.isdigit() and int(target) >= step


class CheckpointManager:
    def __init__(
        self,
        *,
        engine: Engine,
        store: ObjectStore,
        bus: Bus | None,
        bucket: str,
        run_id: uuid.UUID,
        output_dir: Path,
        complete_timeout_s: float = 600.0,
    ) -> None:
        self.engine = engine
        self.store = store
        self.bus = bus
        self.bucket = bucket
        self.run_id = run_id
        self.output_dir = output_dir
        self.complete_timeout_s = complete_timeout_s
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"ckpt-{str(run_id)[:8]}")
        self._futures: list[Future[Uploaded]] = []
        self.last_uploaded: Uploaded | None = None
        self.error: BaseException | None = None
        self.pending_steps: set[int] = set()

    def prefix(self, step: int) -> str:
        return f"runs/{self.run_id}/checkpoints/{step:06d}"

    # -- upload ---------------------------------------------------------------------------------
    def submit(self, step: int) -> Future[Uploaded]:
        self.pending_steps.add(step)
        fut = self._pool.submit(self._upload, step)
        self._futures.append(fut)
        return fut

    def in_flight(self) -> bool:
        return any(not f.done() for f in self._futures)

    def wait_all(self, timeout: float | None = None) -> None:
        for f in list(self._futures):
            try:
                f.result(timeout=timeout)
            except Exception as exc:
                self.error = exc

    def shutdown(self) -> None:
        self._pool.shutdown(wait=True, cancel_futures=False)

    def _wait_complete(self, step: int) -> None:
        deadline = time.monotonic() + self.complete_timeout_s
        while not is_complete(self.output_dir, step):
            if time.monotonic() > deadline:
                raise CheckpointCorruptError(
                    f"checkpoint {step} incomplete after {self.complete_timeout_s:.0f}s"
                )
            time.sleep(1.0)

    def _upload(self, step: int) -> Uploaded:
        try:
            self._wait_complete(step)
            d = ckpt_dir(self.output_dir, step)
            size = self.store.upload_dir(
                d / "pretrained_model", self.bucket, f"{self.prefix(step)}/pretrained_model"
            )
            size += self.store.upload_dir(
                d / "training_state", self.bucket, f"{self.prefix(step)}/training_state"
            )
            prev = self.last_uploaded
            outbox = Outbox()
            with self.engine.begin() as conn:
                conn.execute(
                    update(checkpoints)
                    .where(checkpoints.c.run_id == self.run_id, checkpoints.c.is_last.is_(True))
                    .values(is_last=False, has_training_state=False)
                )
                stmt = pg_insert(checkpoints).values(
                    id=uuid.uuid4(),
                    run_id=self.run_id,
                    step=step,
                    storage_prefix=f"s3://{self.bucket}/{self.prefix(step)}/",
                    size_bytes=size,
                    has_training_state=True,
                    is_last=True,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=[checkpoints.c.run_id, checkpoints.c.step],
                    set_={
                        "size_bytes": size,
                        "has_training_state": True,
                        "is_last": True,
                        "updated_at": utcnow(),
                    },
                )
                conn.execute(stmt)
                ck_id = conn.execute(
                    select(checkpoints.c.id).where(
                        checkpoints.c.run_id == self.run_id, checkpoints.c.step == step
                    )
                ).scalar_one()
                append_run_event(
                    conn,
                    self.run_id,
                    "checkpoint",
                    {
                        "kind": "checkpoint",
                        "step": step,
                        "checkpoint_id": str(ck_id),
                        "size_bytes": size,
                        "ts": iso(utcnow()),
                    },
                    outbox=outbox,
                )
            outbox.flush(self.bus)
            # Only the newest checkpoint keeps training_state (remote and local).
            for old in self._older_remote_states(step):
                self.store.delete_prefix(self.bucket, f"{self.prefix(old)}/training_state")
            self._prune_local(step)
            up = Uploaded(step, ck_id, size)
            self.last_uploaded = up
            log.info("checkpoint %d uploaded (%d bytes, prev=%s)", step, size, prev.step if prev else None)
            return up
        except (StorageError, CheckpointCorruptError, OSError) as exc:
            self.error = exc
            raise
        finally:
            self.pending_steps.discard(step)

    def _older_remote_states(self, step: int) -> list[int]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(checkpoints.c.step).where(
                    checkpoints.c.run_id == self.run_id, checkpoints.c.step != step
                )
            ).scalars()
            return [int(s) for s in rows]

    def _prune_local(self, keep_step: int) -> None:
        root = self.output_dir / "checkpoints"
        if not root.exists():
            return
        for d in root.iterdir():
            if d.is_dir() and not d.is_symlink() and d.name.isdigit() and int(d.name) < keep_step:
                shutil.rmtree(d, ignore_errors=True)

    # -- restore ---------------------------------------------------------------------------------
    def restore(self, step: int) -> Path:
        """Download ``checkpoints/<step>/{pretrained_model,training_state}`` and point ``last`` to it."""
        d = ckpt_dir(self.output_dir, step)
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
        n = self.store.download_prefix(self.bucket, self.prefix(step), d)
        if n == 0 or not (d / "training_state" / "training_step.json").exists():
            raise CheckpointCorruptError(f"checkpoint {step} missing training_state in object storage")
        last = self.output_dir / "checkpoints" / "last"
        if last.is_symlink() or last.exists():
            last.unlink()
        last.symlink_to(f"{step:06d}")
        return d


def download_pretrained(store: ObjectStore, storage_prefix: str, dest: Path) -> Path:
    """Restore ``<checkpoint>/pretrained_model`` (init_from model/checkpoint) into ``dest``."""
    from core.s3 import parse_s3_uri

    bucket, prefix = parse_s3_uri(storage_prefix)
    if dest.exists():
        shutil.rmtree(dest)
    n = store.download_prefix(bucket, prefix.rstrip("/") + "/pretrained_model", dest)
    if n == 0 or not (dest / "config.json").exists():
        raise CheckpointCorruptError(f"no pretrained_model under {storage_prefix}")
    return dest
