"""Build small, real LeRobot datasets (v3.0 and v2.1 layouts) for tests.

Everything is written with pyarrow + PyAV exactly in the on-disk format LeRobot 0.7.1 reads, so the
validator and LeRobot's own converter operate on genuine files (nothing is mocked).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

import av
import numpy as np
import numpy.typing as npt
import pyarrow as pa  # type: ignore[import-untyped]  # pyarrow ships no type information
import pyarrow.parquet as pq  # type: ignore[import-untyped]  # pyarrow ships no type information

JOINTS = [
    "shoulder_pan.pos",
    "shoulder_lift.pos",
    "elbow_flex.pos",
    "wrist_flex.pos",
    "wrist_roll.pos",
    "gripper.pos",
]
CAM = "observation.images.front"
TASK = "Pick the cube"


@dataclass
class SynthSpec:
    episodes: int = 3
    length: int = 40
    fps: int = 30
    width: int = 64
    height: int = 48
    camera: bool = True
    seed: int = 0


def _encode_video(path: Path, frames: npt.NDArray[np.uint8], fps: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with av.open(str(path), mode="w", format="mp4") as c:
        s: Any = c.add_stream("libx264", rate=Fraction(fps))
        s.width, s.height = frames.shape[2], frames.shape[1]
        s.pix_fmt = "yuv420p"
        s.options = {"g": "2", "crf": "30", "preset": "ultrafast"}
        for i, img in enumerate(frames):
            f = av.VideoFrame.from_ndarray(img, format="rgb24")
            f.pts = i
            f.time_base = Fraction(1, fps)
            for p in s.encode(f):
                c.mux(p)
        for p in s.encode(None):
            c.mux(p)


def _frames(spec: SynthSpec, ep: int) -> npt.NDArray[np.uint8]:
    t = np.arange(spec.length)[:, None, None]
    x = np.arange(spec.width)[None, None, :]
    y = np.arange(spec.height)[None, :, None]
    base = (x * 3 + y * 2 + t * 5 + ep * 40) % 256
    img = np.stack([base, (base + 85) % 256, (base + 170) % 256], axis=-1).astype(np.uint8)
    return np.broadcast_to(img, (spec.length, spec.height, spec.width, 3)).copy()


def _features(spec: SynthSpec, version: str) -> dict[str, Any]:
    f: dict[str, Any] = {
        "action": {"dtype": "float32", "shape": [6], "names": list(JOINTS)},
        "observation.state": {"dtype": "float32", "shape": [6], "names": list(JOINTS)},
    }
    if spec.camera:
        f[CAM] = {
            "dtype": "video",
            "shape": [spec.height, spec.width, 3],
            "names": ["height", "width", "channels"],
            "info": {
                "video.height": spec.height,
                "video.width": spec.width,
                "video.codec": "h264",
                "video.pix_fmt": "yuv420p",
                "video.is_depth_map": False,
                "video.fps": spec.fps,
                "video.channels": 3,
                "has_audio": False,
            },
        }
    for k, dt in (
        ("timestamp", "float32"),
        ("frame_index", "int64"),
        ("episode_index", "int64"),
        ("index", "int64"),
        ("task_index", "int64"),
    ):
        f[k] = {"dtype": dt, "shape": [1], "names": None}
    if version == "v2.1":
        for v in f.values():
            if v["dtype"] != "video":
                v["fps"] = float(spec.fps)
    return f


def _episode_table(spec: SynthSpec, ep: int, start_index: int) -> pa.Table:
    rng = np.random.default_rng(spec.seed + ep)
    n = spec.length
    state = (rng.standard_normal((n, 6)) * 10).astype(np.float32)
    action = (state + rng.standard_normal((n, 6)).astype(np.float32)).astype(np.float32)
    ts = (np.arange(n, dtype=np.float64) / spec.fps).astype(np.float32)
    return pa.table(
        {
            "action": pa.FixedSizeListArray.from_arrays(pa.array(action.reshape(-1)), 6),
            "observation.state": pa.FixedSizeListArray.from_arrays(pa.array(state.reshape(-1)), 6),
            "timestamp": pa.array(ts),
            "frame_index": pa.array(np.arange(n, dtype=np.int64)),
            "episode_index": pa.array(np.full(n, ep, dtype=np.int64)),
            "index": pa.array(np.arange(start_index, start_index + n, dtype=np.int64)),
            "task_index": pa.array(np.zeros(n, dtype=np.int64)),
        }
    )


def _stats_of(table: pa.Table, spec: SynthSpec) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k in table.column_names:
        col = table.column(k).combine_chunks()
        if pa.types.is_fixed_size_list(col.type):
            arr = np.asarray(col.flatten().to_numpy(), dtype=np.float64).reshape(-1, col.type.list_size)
        else:
            arr = np.asarray(col.to_numpy(), dtype=np.float64).reshape(-1, 1)
        out[k] = {
            "min": arr.min(0).tolist(),
            "max": arr.max(0).tolist(),
            "mean": arr.mean(0).tolist(),
            "std": arr.std(0).tolist(),
            "count": [int(arr.shape[0])],
        }
    if spec.camera:
        out[CAM] = {
            "min": [[[0.0]], [[0.0]], [[0.0]]],
            "max": [[[1.0]], [[1.0]], [[1.0]]],
            "mean": [[[0.5]], [[0.5]], [[0.5]]],
            "std": [[[0.29]], [[0.29]], [[0.29]]],
            "count": [spec.episodes * spec.length],
        }
    return out


def write_tasks(root: Path, tasks: list[str]) -> None:
    """Same layout as LeRobot's ``write_tasks``: pandas frame indexed by the task string."""
    import pandas as pd  # type: ignore[import-untyped]  # pandas-stubs not installed

    df = pd.DataFrame({"task_index": list(range(len(tasks)))}, index=pd.Index(tasks, name="task"))
    df.to_parquet(root / "meta" / "tasks.parquet")


def make_v30(root: Path, spec: SynthSpec | None = None) -> Path:
    spec = spec or SynthSpec()
    (root / "meta" / "episodes" / "chunk-000").mkdir(parents=True)
    (root / "data" / "chunk-000").mkdir(parents=True)
    tables = [_episode_table(spec, e, e * spec.length) for e in range(spec.episodes)]
    data = pa.concat_tables(tables)
    pq.write_table(data, root / "data" / "chunk-000" / "file-000.parquet")
    if spec.camera:
        frames = np.concatenate([_frames(spec, e) for e in range(spec.episodes)])
        _encode_video(root / "videos" / CAM / "chunk-000" / "file-000.mp4", frames, spec.fps)
    rows: dict[str, list[Any]] = {
        "episode_index": [],
        "tasks": [],
        "length": [],
        "data/chunk_index": [],
        "data/file_index": [],
        "dataset_from_index": [],
        "dataset_to_index": [],
    }
    vcols = [
        f"videos/{CAM}/chunk_index",
        f"videos/{CAM}/file_index",
        f"videos/{CAM}/from_timestamp",
        f"videos/{CAM}/to_timestamp",
    ]
    for c in vcols if spec.camera else []:
        rows[c] = []
    rows["meta/episodes/chunk_index"] = [0] * spec.episodes
    rows["meta/episodes/file_index"] = [0] * spec.episodes
    for e in range(spec.episodes):
        ep_stats = _stats_of(tables[e], SynthSpec(**{**spec.__dict__, "episodes": 1}))
        for feat, st in ep_stats.items():
            for name, val in st.items():
                rows.setdefault(f"stats/{feat}/{name}", []).append(
                    np.asarray(val, dtype=np.float64).reshape(-1).tolist()
                )
        rows["episode_index"].append(e)
        rows["tasks"].append([TASK])
        rows["length"].append(spec.length)
        rows["data/chunk_index"].append(0)
        rows["data/file_index"].append(0)
        rows["dataset_from_index"].append(e * spec.length)
        rows["dataset_to_index"].append((e + 1) * spec.length)
        if spec.camera:
            rows[vcols[0]].append(0)
            rows[vcols[1]].append(0)
            rows[vcols[2]].append(e * spec.length / spec.fps)
            rows[vcols[3]].append((e + 1) * spec.length / spec.fps)
    pq.write_table(pa.table(rows), root / "meta" / "episodes" / "chunk-000" / "file-000.parquet")
    write_tasks(root, [TASK])
    info = {
        "codebase_version": "v3.0",
        "robot_type": "so_follower",
        "total_episodes": spec.episodes,
        "total_frames": spec.episodes * spec.length,
        "total_tasks": 1,
        "chunks_size": 1000,
        "data_files_size_in_mb": 100,
        "video_files_size_in_mb": 200,
        "fps": spec.fps,
        "splits": {"train": f"0:{spec.episodes}"},
        "data_path": "data/chunk-{chunk_index:03d}/file-{file_index:03d}.parquet",
        "video_path": "videos/{video_key}/chunk-{chunk_index:03d}/file-{file_index:03d}.mp4"
        if spec.camera
        else None,
        "features": _features(spec, "v3.0"),
    }
    (root / "meta" / "info.json").write_text(json.dumps(info, indent=2))
    (root / "meta" / "stats.json").write_text(json.dumps(_stats_of(data, spec), indent=2))
    return root


def make_v21(root: Path, spec: SynthSpec | None = None) -> Path:
    """LeRobot codebase v2.1 layout (one parquet / mp4 per episode, jsonl metadata)."""
    spec = spec or SynthSpec()
    (root / "meta").mkdir(parents=True)
    eps, eps_stats = [], []
    for e in range(spec.episodes):
        t = _episode_table(spec, e, e * spec.length)
        p = root / "data" / "chunk-000" / f"episode_{e:06d}.parquet"
        p.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(t, p)
        if spec.camera:
            _encode_video(
                root / "videos" / "chunk-000" / CAM / f"episode_{e:06d}.mp4", _frames(spec, e), spec.fps
            )
        eps.append({"episode_index": e, "tasks": [TASK], "length": spec.length})
        st = _stats_of(t, SynthSpec(**{**spec.__dict__, "episodes": 1}))
        eps_stats.append({"episode_index": e, "stats": st})
    (root / "meta" / "episodes.jsonl").write_text("\n".join(json.dumps(x) for x in eps) + "\n")
    (root / "meta" / "episodes_stats.jsonl").write_text("\n".join(json.dumps(x) for x in eps_stats) + "\n")
    (root / "meta" / "tasks.jsonl").write_text(json.dumps({"task_index": 0, "task": TASK}) + "\n")
    info = {
        "codebase_version": "v2.1",
        "robot_type": "so_follower",
        "total_episodes": spec.episodes,
        "total_frames": spec.episodes * spec.length,
        "total_tasks": 1,
        "total_videos": spec.episodes if spec.camera else 0,
        "total_chunks": 1,
        "chunks_size": 1000,
        "fps": spec.fps,
        "splits": {"train": f"0:{spec.episodes}"},
        "data_path": "data/chunk-{episode_chunk:03d}/episode_{episode_index:06d}.parquet",
        "video_path": "videos/chunk-{episode_chunk:03d}/{video_key}/episode_{episode_index:06d}.mp4"
        if spec.camera
        else None,
        "features": _features(spec, "v2.1"),
    }
    (root / "meta" / "info.json").write_text(json.dumps(info, indent=2))
    return root
