"""``hibiscus watch <dir>``: upload each completed LeRobot recording exactly once.

Each scan:
1. finds dataset roots under ``<dir>`` (the dir itself, or children up to 2 levels deep);
2. skips roots whose current fingerprint is already in the ledger (uploaded before);
3. requires :func:`hibiscus.recording.check_recording` to pass **and** the fingerprint to be
   unchanged for ``debounce_s`` seconds (the recorder may still be writing);
4. uploads via :class:`hibiscus.upload.Uploader` (resumable) and records the fingerprint in the
   ledger ``<state_dir>/watch-ledger.json``. Failed uploads are retried on later scans with a
   growing delay; a re-recorded dataset (new fingerprint) is uploaded again as a **new version of
   the same dataset** (the ledger's ``dataset_id`` is passed to the push function).
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hibiscus.archive import DEFAULT_EXCLUDES, VirtualTar
from hibiscus.config import read_json, state_dir, write_private
from hibiscus.recording import check_recording, find_dataset_roots
from hibiscus.upload import UploadResult


def ledger_path() -> Path:
    return state_dir() / "watch-ledger.json"


@dataclass
class _Pending:
    fingerprint: str
    stable_since: float
    failures: int = 0
    retry_at: float = 0.0
    last_reason: str = ""


@dataclass
class ScanReport:
    uploaded: list[tuple[Path, UploadResult]] = field(default_factory=list)
    waiting: dict[Path, str] = field(default_factory=dict)
    failed: dict[Path, str] = field(default_factory=dict)
    skipped: list[Path] = field(default_factory=list)


PushFn = Callable[[VirtualTar, Path, "str | None"], UploadResult]
"""(source, dataset root, dataset_id of a previous upload of this root or None) -> result"""


class Watcher:
    def __init__(
        self,
        root: Path,
        push: PushFn,
        *,
        debounce_s: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
        excludes: frozenset[str] = DEFAULT_EXCLUDES,
        on_event: Callable[[str, Path, str], None] = lambda kind, path, msg: None,
    ) -> None:
        self.root = root.resolve()
        self.push = push
        self.debounce_s = debounce_s
        self.clock = clock
        self.excludes = excludes
        self.on_event = on_event
        self._pending: dict[Path, _Pending] = {}
        self._ledger = self._load_ledger()

    # ------------------------------------------------------------------ ledger
    def _load_ledger(self) -> dict[str, dict[str, Any]]:
        try:
            data = read_json(ledger_path()) or {}
        except (ValueError, json.JSONDecodeError):
            data = {}
        return {str(k): v for k, v in data.items() if isinstance(v, dict)}

    def _save_ledger(self) -> None:
        write_private(ledger_path(), json.dumps(self._ledger, indent=2, sort_keys=True) + "\n")

    def already_uploaded(self, root: Path, fingerprint: str) -> bool:
        entry = self._ledger.get(str(root))
        return bool(entry and entry.get("fingerprint") == fingerprint)

    # ------------------------------------------------------------------ scan
    def scan(self) -> ScanReport:
        report = ScanReport()
        now = self.clock()
        for ds in find_dataset_roots(self.root):
            ds = ds.resolve()
            try:
                src = VirtualTar(ds, excludes=self.excludes)
            except (OSError, ValueError) as exc:
                report.waiting[ds] = f"unreadable: {exc}"
                continue
            fp = src.fingerprint()
            if self.already_uploaded(ds, fp):
                report.skipped.append(ds)
                self._pending.pop(ds, None)
                continue
            pend = self._pending.get(ds)
            if pend is None or pend.fingerprint != fp:
                pend = _Pending(fingerprint=fp, stable_since=now)
                self._pending[ds] = pend
            status = check_recording(ds)
            if not status.complete:
                reason = "; ".join(status.reasons[:3])
                if reason != pend.last_reason:
                    self.on_event("waiting", ds, reason)
                    pend.last_reason = reason
                report.waiting[ds] = reason
                continue
            quiet_for = now - pend.stable_since
            if quiet_for < self.debounce_s:
                report.waiting[ds] = f"settling ({quiet_for:.0f}/{self.debounce_s:.0f}s without changes)"
                continue
            if now < pend.retry_at:
                report.waiting[ds] = f"retrying in {pend.retry_at - now:.0f}s"
                continue
            self.on_event("uploading", ds, f"{status.total_episodes} episodes, {src.size} bytes")
            try:
                prev = self._ledger.get(str(ds), {}).get("dataset_id")
                result = self.push(src, ds, str(prev) if prev else None)
            except Exception as exc:
                pend.failures += 1
                pend.retry_at = now + min(600.0, 15.0 * (2 ** (pend.failures - 1)))
                report.failed[ds] = str(exc)
                self.on_event("failed", ds, str(exc))
                continue
            self._ledger[str(ds)] = {
                "fingerprint": fp,
                "dataset_id": result.dataset_id,
                "version_id": result.version_id,
                "version": result.version,
                "sha256": result.sha256,
                "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            self._save_ledger()
            self._pending.pop(ds, None)
            report.uploaded.append((ds, result))
            self.on_event("uploaded", ds, f"{result.dataset_name} v{result.version}")
        return report
