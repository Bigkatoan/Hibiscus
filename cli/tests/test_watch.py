from __future__ import annotations

import json
import os
import struct
from pathlib import Path

import pytest

from hibiscus.api import HibiscusApi
from hibiscus.archive import VirtualTar
from hibiscus.recording import check_recording, find_dataset_roots, mp4_finalized, parquet_closed
from hibiscus.upload import MIB, Uploader, UploadResult
from hibiscus.watch import Watcher, ledger_path
from tests.conftest import GOLDEN_DATASET
from tests.fake_server import FakeHibiscus

CAM = "observation.images.wrist_cam"


def _box(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(payload), kind) + payload


def _mp4(moov: bool = True) -> bytes:
    data = _box(b"ftyp", b"isom" + b"\0" * 8) + _box(b"mdat", os.urandom(4000))
    return data + (_box(b"moov", b"\0" * 100) if moov else b"")


def _parquet(closed: bool = True) -> bytes:
    return b"PAR1" + os.urandom(500) + (b"\x10\0\0\0PAR1" if closed else b"")


def make_recording(root: Path, *, episodes: int = 2) -> Path:
    (root / "meta" / "episodes" / "chunk-000").mkdir(parents=True)
    (root / "data" / "chunk-000").mkdir(parents=True)
    (root / "videos" / CAM / "chunk-000").mkdir(parents=True)
    info = {
        "codebase_version": "v3.0",
        "fps": 30,
        "robot_type": "so_follower",
        "total_episodes": episodes,
        "features": {
            "action": {"dtype": "float32", "shape": [6]},
            CAM: {"dtype": "video", "shape": [360, 640, 3]},
        },
    }
    (root / "meta" / "info.json").write_text(json.dumps(info))
    (root / "meta" / "stats.json").write_text("{}")
    (root / "meta" / "tasks.parquet").write_bytes(_parquet())
    (root / "meta" / "episodes" / "chunk-000" / "file-000.parquet").write_bytes(_parquet())
    (root / "data" / "chunk-000" / "file-000.parquet").write_bytes(_parquet())
    (root / "videos" / CAM / "chunk-000" / "file-000.mp4").write_bytes(_mp4())
    return root


def test_complete_recording_detected(tmp_path: Path) -> None:
    st = check_recording(make_recording(tmp_path / "rec"))
    assert st.complete, st.reasons
    assert st.total_episodes == 2 and st.fps == 30 and st.robot_type == "so_follower"


@pytest.mark.skipif(not GOLDEN_DATASET.is_dir(), reason="golden dataset not present")
def test_golden_dataset_is_complete() -> None:
    st = check_recording(GOLDEN_DATASET)
    assert st.complete, st.reasons
    assert st.total_episodes == 20
    assert mp4_finalized(GOLDEN_DATASET / "videos" / CAM / "chunk-000" / "file-000.mp4")
    assert parquet_closed(GOLDEN_DATASET / "data" / "chunk-000" / "file-000.parquet")


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (
            lambda r: (r / "data/chunk-000/file-000.parquet").write_bytes(_parquet(closed=False)),
            "not finalized",
        ),
        (lambda r: (r / f"videos/{CAM}/chunk-000/file-000.mp4").write_bytes(_mp4(moov=False)), "encoding"),
        (lambda r: (r / f"videos/{CAM}/chunk-000/file-000.mp4").write_bytes(_mp4()[:-10]), "encoding"),
        (
            lambda r: (
                (r / "images" / CAM).mkdir(parents=True),
                (r / "images" / CAM / "f.png").write_bytes(b"x"),
            ),
            "images/",
        ),
        (lambda r: (r / "meta/stats.json").unlink(), "stats.json missing"),
        (
            lambda r: (r / "meta/info.json").write_text(
                json.dumps({"codebase_version": "v2.1", "total_episodes": 0})
            ),
            "v2.1",
        ),
        (lambda r: (r / "meta/info.json").write_text("{not json"), "unreadable"),
    ],
)
def test_incomplete_recordings(tmp_path: Path, mutate: object, reason: str) -> None:
    rec = make_recording(tmp_path / "rec")
    mutate(rec)  # type: ignore[operator]
    st = check_recording(rec)
    assert not st.complete
    assert any(reason in r for r in st.reasons), st.reasons


def test_find_dataset_roots(tmp_path: Path) -> None:
    make_recording(tmp_path / "a")
    make_recording(tmp_path / "user" / "b")
    make_recording(tmp_path / ".hidden")
    (tmp_path / "empty").mkdir()
    assert find_dataset_roots(tmp_path) == [tmp_path / "a", tmp_path / "user" / "b"]
    assert find_dataset_roots(tmp_path / "a") == [tmp_path / "a"]


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def test_watcher_debounces_and_uploads_once(fake: FakeHibiscus, api: HibiscusApi, tmp_path: Path) -> None:
    root = tmp_path / "recordings"
    rec = make_recording(root / "session1")
    (rec / "data" / "chunk-000" / "file-000.parquet").write_bytes(_parquet(closed=False))  # still recording
    clock = Clock()
    events: list[tuple[str, str]] = []

    def push(src: VirtualTar, ds: Path, prev: str | None) -> UploadResult:
        if prev:
            return Uploader(api).push(src, dataset_id=prev, part_size=5 * MIB)
        return Uploader(api).push(src, new_dataset_name=ds.name, part_size=5 * MIB)

    w = Watcher(root, push, debounce_s=30, clock=clock, on_event=lambda k, p, m: events.append((k, p.name)))
    r = w.scan()
    assert not r.uploaded and "not finalized" in r.waiting[rec.resolve()]
    # recording finishes (file changes) -> debounce restarts
    clock.t += 5
    (rec / "data" / "chunk-000" / "file-000.parquet").write_bytes(_parquet())
    r = w.scan()
    assert not r.uploaded and "settling" in r.waiting[rec.resolve()]
    clock.t += 29
    assert not w.scan().uploaded
    clock.t += 2
    r = w.scan()
    assert len(r.uploaded) == 1
    assert [e for e in events if e[0] == "uploaded"] == [("uploaded", "session1")]
    # nothing changes -> never uploaded again, also by a brand-new watcher (ledger on disk)
    clock.t += 100
    assert w.scan().skipped == [rec.resolve()]
    w2 = Watcher(root, push, debounce_s=0, clock=clock)
    assert w2.scan().skipped == [rec.resolve()]
    assert len(fake.uploads) == 1
    ledger = json.loads(ledger_path().read_text())
    assert ledger[str(rec.resolve())]["version"] == 1
    assert ledger_path().stat().st_mode & 0o777 == 0o600
    # re-recording (resume adds an episode) -> new fingerprint -> uploaded again as a new version
    (rec / "data" / "chunk-000" / "file-001.parquet").write_bytes(_parquet())
    assert len(w2.scan().uploaded) == 1  # debounce 0: uploaded on first sight
    assert w2.scan().skipped == [rec.resolve()]
    assert len(fake.uploads) == 2
    second = fake.uploads[list(fake.uploads)[1]]["completed_body"]
    assert second["dataset"]["name"] == "session1" and second["version"]["version"] == 2
    assert len(fake.datasets) == 1


def test_watcher_retries_failed_upload_later(tmp_path: Path) -> None:
    root = tmp_path / "rec"
    make_recording(root / "s")
    clock = Clock()
    calls: list[int] = []

    def push(src: VirtualTar, ds: Path, prev: str | None) -> UploadResult:
        calls.append(1)
        if len(calls) == 1:
            raise ConnectionError("network down")
        return UploadResult("u", "d", "s", "v", 1, "j", 0, 1, "0" * 64, src.size)

    w = Watcher(root, push, debounce_s=0, clock=clock)
    r = w.scan()
    assert r.failed and not r.uploaded
    r = w.scan()
    assert "retrying" in next(iter(r.waiting.values()))
    clock.t += 16
    assert len(w.scan().uploaded) == 1
    assert len(calls) == 2
