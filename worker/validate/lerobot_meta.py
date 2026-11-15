"""Read LeRobot v3.0 metadata with pyarrow only (no Hub access, no LeRobotDataset construction).

Layout (LeRobot 0.7.1, codebase v3.0)::

    meta/info.json  meta/stats.json  meta/tasks.parquet  meta/episodes/chunk-XXX/file-XXX.parquet
    data/chunk-XXX/file-XXX.parquet  videos/<video_key>/chunk-XXX/file-XXX.mp4
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq  # type: ignore[import-untyped]  # pyarrow ships no type information

DEFAULT_DATA_PATH = "data/chunk-{chunk_index:03d}/file-{file_index:03d}.parquet"
DEFAULT_VIDEO_PATH = "videos/{video_key}/chunk-{chunk_index:03d}/file-{file_index:03d}.mp4"
INDEX_FEATURES = ("timestamp", "frame_index", "episode_index", "index", "task_index")
VISUAL_DTYPES = ("video", "image")


class MetaError(Exception):
    def __init__(self, code: str, message: str, path: str | None = None, **params: Any) -> None:
        super().__init__(message)
        self.code = code
        self.path = path
        self.params = params


@dataclass(slots=True)
class VideoRef:
    chunk_index: int
    file_index: int
    from_timestamp: float
    to_timestamp: float


@dataclass(slots=True)
class EpisodeMeta:
    index: int
    length: int
    tasks: list[str]
    data_chunk: int
    data_file: int
    from_index: int
    to_index: int
    videos: dict[str, VideoRef] = field(default_factory=dict)


@dataclass(slots=True)
class DatasetMeta:
    root: Path
    info: dict[str, Any]
    episodes: list[EpisodeMeta]
    tasks: list[str]

    @property
    def features(self) -> dict[str, Any]:
        f = self.info.get("features")
        return f if isinstance(f, dict) else {}

    @property
    def fps(self) -> float:
        return float(self.info["fps"])

    @property
    def video_keys(self) -> list[str]:
        return [k for k, v in self.features.items() if isinstance(v, dict) and v.get("dtype") == "video"]

    @property
    def image_keys(self) -> list[str]:
        return [k for k, v in self.features.items() if isinstance(v, dict) and v.get("dtype") == "image"]

    @property
    def camera_keys(self) -> list[str]:
        return self.video_keys + self.image_keys

    @property
    def data_path_template(self) -> str:
        return str(self.info.get("data_path") or DEFAULT_DATA_PATH)

    @property
    def video_path_template(self) -> str:
        return str(self.info.get("video_path") or DEFAULT_VIDEO_PATH)

    def data_path(self, chunk: int, file: int) -> str:
        return self.data_path_template.format(chunk_index=chunk, file_index=file)

    def video_path(self, key: str, ref: VideoRef) -> str:
        return self.video_path_template.format(
            video_key=key, chunk_index=ref.chunk_index, file_index=ref.file_index
        )

    def data_files(self) -> list[tuple[int, int]]:
        return sorted({(e.data_chunk, e.data_file) for e in self.episodes})


def load_info(root: Path) -> dict[str, Any]:
    p = root / "meta" / "info.json"
    if not p.is_file():
        raise MetaError("missing_file", "meta/info.json not found", path="meta/info.json")
    if p.stat().st_size > 16 * 1024 * 1024:
        raise MetaError("info_json_invalid", "meta/info.json is too large", path="meta/info.json")
    try:
        info = json.loads(p.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MetaError(
            "info_json_invalid", f"meta/info.json is not valid JSON: {exc}", path="meta/info.json"
        ) from exc
    if not isinstance(info, dict):
        raise MetaError("info_json_invalid", "meta/info.json must be an object", path="meta/info.json")
    for key in ("codebase_version", "fps", "features"):
        if key not in info:
            raise MetaError(
                "info_json_invalid", f"meta/info.json lacks '{key}'", path="meta/info.json", key=key
            )
    if not isinstance(info["features"], dict) or not info["features"]:
        raise MetaError("info_json_invalid", "'features' must be a non-empty object", path="meta/info.json")
    fps = info["fps"]
    if isinstance(fps, bool) or not isinstance(fps, int | float) or not math.isfinite(fps) or fps <= 0:
        raise MetaError("info_json_invalid", "'fps' must be a positive number", path="meta/info.json")
    return info


def load_tasks(root: Path) -> list[str]:
    p = root / "meta" / "tasks.parquet"
    if not p.is_file():
        raise MetaError("missing_file", "meta/tasks.parquet not found", path="meta/tasks.parquet")
    table = pq.read_table(p)
    cols = table.column_names
    # LeRobot writes a pandas frame indexed by the task string: the index is stored either as a named
    # column "task" or (older writers, e.g. lerobot/pusht) as the unnamed "__index_level_0__".
    task_col = "task" if "task" in cols else None
    if task_col is None:
        meta = table.schema.pandas_metadata or {}
        idx = [c for c in meta.get("index_columns", []) if isinstance(c, str) and c in cols]
        task_col = idx[0] if idx else None
    if task_col is None or "task_index" not in cols:
        raise MetaError(
            "task_missing", "meta/tasks.parquet lacks task / task_index columns", path="meta/tasks.parquet"
        )
    pairs = sorted(
        zip(table.column("task_index").to_pylist(), table.column(task_col).to_pylist(), strict=True)
    )
    return [str(t) for _, t in pairs]


def _episode_files(root: Path) -> list[Path]:
    d = root / "meta" / "episodes"
    files = sorted(d.glob("chunk-*/file-*.parquet")) if d.is_dir() else []
    if not files:
        raise MetaError("missing_file", "meta/episodes/*/*.parquet not found", path="meta/episodes")
    return files


def load_episodes(root: Path, video_keys: list[str]) -> list[EpisodeMeta]:
    required = [
        "episode_index",
        "length",
        "data/chunk_index",
        "data/file_index",
        "dataset_from_index",
        "dataset_to_index",
    ]
    vcols = [
        f"videos/{k}/{c}"
        for k in video_keys
        for c in ("chunk_index", "file_index", "from_timestamp", "to_timestamp")
    ]
    episodes: list[EpisodeMeta] = []
    for f in _episode_files(root):
        rel = f.relative_to(root).as_posix()
        schema_names = pq.read_schema(f).names
        missing = [c for c in [*required, *vcols] if c not in schema_names]
        if missing:
            raise MetaError(
                "missing_file", f"{rel} lacks columns {missing[:5]}", path=rel, columns=missing[:20]
            )
        cols = [*required, *vcols] + (["tasks"] if "tasks" in schema_names else [])
        table = pq.read_table(f, columns=cols)
        for row in table.to_pylist():
            videos = {
                k: VideoRef(
                    int(row[f"videos/{k}/chunk_index"]),
                    int(row[f"videos/{k}/file_index"]),
                    float(row[f"videos/{k}/from_timestamp"]),
                    float(row[f"videos/{k}/to_timestamp"]),
                )
                for k in video_keys
            }
            tasks = row.get("tasks") or []
            episodes.append(
                EpisodeMeta(
                    index=int(row["episode_index"]),
                    length=int(row["length"]),
                    tasks=[str(t) for t in tasks],
                    data_chunk=int(row["data/chunk_index"]),
                    data_file=int(row["data/file_index"]),
                    from_index=int(row["dataset_from_index"]),
                    to_index=int(row["dataset_to_index"]),
                    videos=videos,
                )
            )
    episodes.sort(key=lambda e: e.index)
    return episodes


def load_meta(root: Path) -> DatasetMeta:
    info = load_info(root)
    tasks = load_tasks(root)
    video_keys = [k for k, v in info["features"].items() if isinstance(v, dict) and v.get("dtype") == "video"]
    episodes = load_episodes(root, video_keys)
    return DatasetMeta(root=root, info=info, episodes=episodes, tasks=tasks)


def load_stats(root: Path) -> dict[str, Any] | None:
    p = root / "meta" / "stats.json"
    if not p.is_file():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def find_dataset_roots(base: Path, max_depth: int = 6) -> list[Path]:
    """Directories below ``base`` (inclusive) that contain ``meta/info.json``; nested roots are not
    descended into (a dataset's own subfolders are never treated as a second dataset)."""
    found: list[Path] = []

    def walk(d: Path, depth: int) -> None:
        if (d / "meta" / "info.json").is_file():
            found.append(d)
            return
        if depth >= max_depth:
            return
        for child in sorted(d.iterdir()):
            if child.is_dir() and not child.is_symlink():
                walk(child, depth + 1)

    walk(base, 0)
    return found
