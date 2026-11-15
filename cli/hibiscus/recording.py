"""Detect *completed* LeRobot v3.0 recordings on disk (no LeRobot / pyarrow import needed).

A recording written by ``lerobot-record`` is considered complete when ``dataset.finalize()`` has
run, which we observe from the files it leaves behind:

* ``meta/info.json`` parses, ``codebase_version`` is ``v3.x`` and ``total_episodes >= 1``;
* ``meta/stats.json``, ``meta/tasks.parquet``, ≥ 1 ``meta/episodes/**.parquet`` and
  ≥ 1 ``data/**.parquet`` exist;
* every ``*.parquet`` has both the leading and trailing ``PAR1`` magic — an open
  ``pq.ParquetWriter`` (recording still running, or crashed before finalize) has no footer;
* every video feature has ≥ 1 ``videos/<key>/**.mp4`` and every mp4's top-level box chain is
  intact and contains ``moov`` (the encoder writes it on close);
* the temporary frame directory ``images/`` (``<root>/images``, deleted after encoding) holds
  no files.

Quiescence (nothing changed for ``debounce`` seconds) is checked separately by the watcher.
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from pathlib import Path

PAR1 = b"PAR1"


@dataclass
class RecordingStatus:
    root: Path
    complete: bool
    reasons: list[str] = field(default_factory=list)
    total_episodes: int = 0
    fps: float | None = None
    robot_type: str | None = None


def is_dataset_root(path: Path) -> bool:
    return (path / "meta" / "info.json").is_file()


def parquet_closed(path: Path) -> bool:
    try:
        size = path.stat().st_size
        if size < 12:
            return False
        with path.open("rb") as fh:
            head = fh.read(4)
            fh.seek(size - 4)
            tail = fh.read(4)
    except OSError:
        return False
    return head == PAR1 and tail == PAR1


def mp4_finalized(path: Path) -> bool:
    """True when the top-level ISO-BMFF box chain covers the file exactly and has a ``moov``."""
    try:
        size = path.stat().st_size
        seen_moov = False
        with path.open("rb") as fh:
            pos = 0
            while pos < size:
                fh.seek(pos)
                hdr = fh.read(8)
                if len(hdr) < 8:
                    return False
                box_size, box_type = struct.unpack(">I4s", hdr)
                if box_size == 1:
                    ext = fh.read(8)
                    if len(ext) < 8:
                        return False
                    (box_size,) = struct.unpack(">Q", ext)
                elif box_size == 0:
                    box_size = size - pos  # box extends to EOF
                if box_size < 8 or pos + box_size > size:
                    return False
                if box_type == b"moov":
                    seen_moov = True
                pos += box_size
        return seen_moov
    except OSError:
        return False


def check_recording(root: Path) -> RecordingStatus:
    st = RecordingStatus(root=root, complete=False)
    info_path = root / "meta" / "info.json"
    try:
        info = json.loads(info_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        st.reasons.append("meta/info.json missing")
        return st
    except (OSError, ValueError) as exc:
        st.reasons.append(f"meta/info.json unreadable: {exc}")
        return st
    if not isinstance(info, dict):
        st.reasons.append("meta/info.json is not an object")
        return st
    version = str(info.get("codebase_version", ""))
    if not version.startswith("v3"):
        st.reasons.append(f"codebase_version {version or '?'} is not v3.x")
    try:
        st.total_episodes = int(info.get("total_episodes") or 0)
    except (TypeError, ValueError):
        st.total_episodes = 0
    if st.total_episodes < 1:
        st.reasons.append("no episodes saved yet")
    fps = info.get("fps")
    st.fps = float(fps) if isinstance(fps, (int, float)) else None
    rt = info.get("robot_type")
    st.robot_type = str(rt) if rt else None

    for rel in ("meta/stats.json", "meta/tasks.parquet"):
        if not (root / rel).is_file():
            st.reasons.append(f"{rel} missing")
    ep_files = sorted((root / "meta" / "episodes").rglob("*.parquet"))
    data_files = sorted((root / "data").rglob("*.parquet"))
    if not ep_files:
        st.reasons.append("meta/episodes/*.parquet missing")
    if not data_files:
        st.reasons.append("data/*.parquet missing")
    for pq in [root / "meta" / "tasks.parquet", *ep_files, *data_files]:
        if pq.is_file() and not parquet_closed(pq):
            st.reasons.append(f"{pq.relative_to(root)} not finalized (parquet footer missing)")

    features = info.get("features") or {}
    video_keys = [k for k, v in features.items() if isinstance(v, dict) and v.get("dtype") == "video"]
    for key in video_keys:
        mp4s = sorted((root / "videos" / key).rglob("*.mp4"))
        if not mp4s:
            st.reasons.append(f"videos/{key} has no mp4 yet")
        for mp4 in mp4s:
            if not mp4_finalized(mp4):
                st.reasons.append(f"{mp4.relative_to(root)} not finalized (encoding in progress)")
    images = root / "images"
    if images.is_dir() and any(p.is_file() for p in images.rglob("*")):
        st.reasons.append("images/ still holds frames waiting for video encoding")

    st.complete = not st.reasons
    return st


def find_dataset_roots(path: Path, max_depth: int = 2) -> list[Path]:
    """``path`` itself if it is a dataset, else dataset roots up to ``max_depth`` levels below."""
    if is_dataset_root(path):
        return [path]
    found: list[Path] = []

    def rec(d: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            children = sorted(p for p in d.iterdir() if p.is_dir() and not p.name.startswith("."))
        except OSError:
            return
        for c in children:
            if is_dataset_root(c):
                found.append(c)
            else:
                rec(c, depth + 1)

    rec(path, 1)
    return found
