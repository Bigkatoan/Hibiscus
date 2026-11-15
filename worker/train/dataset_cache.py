"""Local LeRobot dataset cache ``/cache/datasets/<version_id>/`` (run-lifecycle §10).

* download every object under ``dataset_versions.storage_prefix`` (unpacked by A3's validator);
* verify ``content_hash`` = sha256 over sorted ``<relative path>\\0<sha256(file)>\\n`` (db-schema.md);
* ``.complete`` marker holds the hash; an ``fcntl`` lock serialises workers sharing ``/cache``;
* LRU eviction by marker mtime when the cache exceeds ``max_bytes``.
"""

from __future__ import annotations

import fcntl
import hashlib
import logging
import shutil
from pathlib import Path

from core.s3 import ObjectStore, StorageError, parse_s3_uri

log = logging.getLogger(__name__)
MARKER = ".complete"


class DatasetUnavailableError(RuntimeError):
    """Maps to run error ``dataset_unavailable`` (infra)."""


def content_hash(root: Path) -> str:
    lines = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or (p.parent == root and p.name == MARKER):
            continue
        h = hashlib.sha256()
        with p.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        lines.append(f"{p.relative_to(root).as_posix()}\0{h.hexdigest()}\n")
    outer = hashlib.sha256()
    for line in sorted(lines):
        outer.update(line.encode())
    return outer.hexdigest()


def _dir_size(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


class DatasetCache:
    def __init__(self, root: Path, store: ObjectStore, max_bytes: int) -> None:
        self.root = root / "datasets"
        self.store = store
        self.max_bytes = max_bytes

    def path(self, version_id: str) -> Path:
        return self.root / version_id

    def ensure(self, version_id: str, storage_prefix: str, expected_hash: str | None) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        dest = self.path(version_id)
        lock_path = self.root / f".{version_id}.lock"
        with lock_path.open("w") as lockf:
            fcntl.flock(lockf, fcntl.LOCK_EX)
            marker = dest / MARKER
            if marker.exists() and (expected_hash is None or marker.read_text().strip() == expected_hash):
                marker.touch()
                return dest
            if dest.exists():
                shutil.rmtree(dest)
            tmp = self.root / f".{version_id}.partial"
            if tmp.exists():
                shutil.rmtree(tmp)
            tmp.mkdir(parents=True)
            try:
                bucket, prefix = parse_s3_uri(storage_prefix)
                n = self.store.download_prefix(bucket, prefix, tmp)
            except (StorageError, ValueError) as exc:
                shutil.rmtree(tmp, ignore_errors=True)
                raise DatasetUnavailableError(f"download failed: {exc}") from exc
            if n == 0 or not (tmp / "meta" / "info.json").exists():
                shutil.rmtree(tmp, ignore_errors=True)
                raise DatasetUnavailableError(f"no LeRobot dataset under {storage_prefix}")
            got = content_hash(tmp)
            if expected_hash is not None and got != expected_hash:
                shutil.rmtree(tmp, ignore_errors=True)
                raise DatasetUnavailableError(f"content hash mismatch: expected {expected_hash}, got {got}")
            (tmp / MARKER).write_text(got)
            tmp.rename(dest)
            log.info("dataset %s cached (%d bytes)", version_id, n)
        self.evict(keep={version_id})
        return dest

    def evict(self, keep: set[str]) -> None:
        if not self.root.exists():
            return
        entries = [d for d in self.root.iterdir() if d.is_dir() and (d / MARKER).exists()]
        sizes = {d: _dir_size(d) for d in entries}
        total = sum(sizes.values())
        for d in sorted(entries, key=lambda d: (d / MARKER).stat().st_mtime):
            if total <= self.max_bytes:
                break
            if d.name in keep:
                continue
            shutil.rmtree(d, ignore_errors=True)
            total -= sizes[d]
