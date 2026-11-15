"""The five LeRobot validation steps (PLAN 3.2): structure, schema, decode, timestamps, stats."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeGuard

import numpy as np
import numpy.typing as npt
import pyarrow as pa  # type: ignore[import-untyped]  # pyarrow ships no type information
import pyarrow.parquet as pq  # type: ignore[import-untyped]  # pyarrow ships no type information

from validate import video
from validate.lerobot_meta import INDEX_FEATURES, VISUAL_DTYPES, DatasetMeta, EpisodeMeta
from validate.report import IssueCode, Step

Progress = Callable[[float], None]
FloatArray = npt.NDArray[np.float64]

TIMESTAMP_TOLERANCE_S = 1e-4  # LeRobot default tolerance_s
STATS_WARN_REL_DIFF = 1e-3
MIN_EPISODE_FRAMES = 2


def _noop(_: float) -> None:
    return None


# --------------------------------------------------------------------------------------------------
# structure
# --------------------------------------------------------------------------------------------------
def check_structure(meta: DatasetMeta, step: Step) -> None:
    root = meta.root
    info = meta.info
    if not meta.episodes:
        step.error(IssueCode.MISSING_FILE, "Dataset has no episodes", path="meta/episodes")
        return
    indices = [e.index for e in meta.episodes]
    if indices != list(range(len(indices))):
        step.error(
            IssueCode.INFO_JSON_INVALID,
            "Episode indices are not contiguous from 0",
            path="meta/episodes",
            params={"first_gap": next((i for i, v in enumerate(indices) if v != i), None)},
        )
    total_eps = info.get("total_episodes")
    if total_eps is not None and total_eps != len(meta.episodes):
        step.error(
            IssueCode.INFO_JSON_INVALID,
            "total_episodes does not match meta/episodes",
            path="meta/info.json",
            params={"info": total_eps, "actual": len(meta.episodes)},
        )
    total_frames = info.get("total_frames")
    actual_frames = sum(e.length for e in meta.episodes)
    if total_frames is not None and total_frames != actual_frames:
        step.error(
            IssueCode.FRAME_COUNT_MISMATCH,
            "total_frames does not match the sum of episode lengths",
            path="meta/info.json",
            params={"info": total_frames, "actual": actual_frames},
        )
    for chunk, file in meta.data_files():
        rel = meta.data_path(chunk, file)
        if not (root / rel).is_file():
            step.error(IssueCode.MISSING_FILE, "Data file missing", path=rel)
    seen: set[str] = set()
    for e in meta.episodes:
        for key, ref in e.videos.items():
            rel = meta.video_path(key, ref)
            if rel in seen:
                continue
            seen.add(rel)
            if not (root / rel).is_file():
                step.error(
                    IssueCode.VIDEO_MISSING,
                    "Video file missing",
                    path=rel,
                    feature=key,
                    episode_index=e.index,
                )


# --------------------------------------------------------------------------------------------------
# schema
# --------------------------------------------------------------------------------------------------
def _valid_shape(shape: Any) -> TypeGuard[list[int]]:
    return (
        isinstance(shape, list)
        and len(shape) >= 1
        and all(isinstance(x, int) and not isinstance(x, bool) and x > 0 for x in shape)
    )


def _names_list(spec: dict[str, Any]) -> list[str] | None:
    names = spec.get("names")
    if isinstance(names, list) and all(isinstance(n, str) for n in names):
        return list(names)
    if isinstance(names, dict):  # older style {"motors": [...]}
        vals = next(iter(names.values()), None)
        if isinstance(vals, list) and all(isinstance(n, str) for n in vals):
            return list(vals)
    return None


def joint_names(meta: DatasetMeta) -> list[str]:
    for key in ("observation.state", "action"):
        spec = meta.features.get(key)
        if isinstance(spec, dict):
            names = _names_list(spec)
            if names:
                return names
    return []


def check_schema(meta: DatasetMeta, step: Step) -> None:
    feats = meta.features
    for key, spec in feats.items():
        if not isinstance(spec, dict) or not isinstance(spec.get("dtype"), str):
            step.error(
                IssueCode.FEATURE_SHAPE_INVALID, "Feature lacks a dtype", feature=key, path="meta/info.json"
            )
            continue
        if not _valid_shape(spec.get("shape")):
            step.error(
                IssueCode.FEATURE_SHAPE_INVALID,
                "Feature shape must be a non-empty list of positive integers",
                feature=key,
                params={"shape": spec.get("shape")},
            )
    if "action" not in feats:
        step.error(IssueCode.FEATURE_MISSING, "Feature 'action' is required", feature="action")
    if "observation.state" not in feats:
        step.warn(
            IssueCode.FEATURE_MISSING, "Feature 'observation.state' is missing", feature="observation.state"
        )
    for key in INDEX_FEATURES:
        if key not in feats:
            step.error(IssueCode.FEATURE_MISSING, f"Feature '{key}' is required", feature=key)

    for key in ("action", "observation.state"):
        spec = feats.get(key)
        if not isinstance(spec, dict) or not _valid_shape(spec.get("shape")):
            continue
        shape = spec["shape"]
        if len(shape) != 1:
            step.error(
                IssueCode.FEATURE_SHAPE_INVALID, f"'{key}' must be 1-D", feature=key, params={"shape": shape}
            )
            continue
        names = _names_list(spec)
        if names is None:
            step.warn(IssueCode.JOINT_NAMES_MISMATCH, f"'{key}' has no joint names", feature=key)
        elif len(names) != shape[0]:
            step.error(
                IssueCode.JOINT_NAMES_MISMATCH,
                f"'{key}' names do not match its shape",
                feature=key,
                params={"names": len(names), "dim": shape[0]},
            )
    a, s = feats.get("action"), feats.get("observation.state")
    if isinstance(a, dict) and isinstance(s, dict):
        an, sn = _names_list(a), _names_list(s)
        if an is not None and sn is not None and an != sn:
            step.warn(
                IssueCode.JOINT_NAMES_MISMATCH,
                "action and observation.state joint names differ",
                feature="action",
                params={"action": an[:32], "observation.state": sn[:32]},
            )

    cams = meta.camera_keys
    if not cams:
        step.warn(IssueCode.NO_CAMERA, "Dataset has no camera feature (image-based policies cannot train)")
    for key in meta.video_keys:
        spec = feats[key]
        shape = spec.get("shape")
        if not _valid_shape(shape) or len(shape) != 3:
            step.error(IssueCode.CAMERA_SHAPE_MISMATCH, "Camera shape must be [H, W, C]", feature=key)
            continue
        names = spec.get("names")
        h, w = (shape[0], shape[1]) if names != ["channels", "height", "width"] else (shape[1], shape[2])
        vinfo = spec.get("info") or {}
        if isinstance(vinfo, dict):
            vh, vw = vinfo.get("video.height"), vinfo.get("video.width")
            if (vh is not None and vh != h) or (vw is not None and vw != w):
                step.error(
                    IssueCode.CAMERA_SHAPE_MISMATCH,
                    "video.height/width disagree with the feature shape",
                    feature=key,
                    params={"shape": shape, "video.height": vh, "video.width": vw},
                )

    # Data parquet columns vs non-visual features.
    non_visual = {
        k: v for k, v in feats.items() if isinstance(v, dict) and v.get("dtype") not in VISUAL_DTYPES
    }
    for chunk, file in meta.data_files():
        p = meta.root / meta.data_path(chunk, file)
        if not p.is_file():
            continue
        rel = meta.data_path(chunk, file)
        try:
            schema = pq.read_schema(p)
        except (pa.ArrowException, OSError) as exc:
            step.error(IssueCode.MISSING_FILE, f"Data file unreadable: {exc}", path=rel)
            continue
        for key, spec in non_visual.items():
            if key not in schema.names:
                step.error(
                    IssueCode.FEATURE_MISSING, f"Column '{key}' missing in data file", feature=key, path=rel
                )
                continue
            shape = spec.get("shape")
            t = schema.field(key).type
            if _valid_shape(shape) and pa.types.is_fixed_size_list(t):
                if t.list_size != math.prod(shape):
                    step.error(
                        IssueCode.FEATURE_SHAPE_INVALID,
                        "Column width does not match the feature shape",
                        feature=key,
                        path=rel,
                        params={"shape": shape, "column_width": t.list_size},
                    )

    # Tasks.
    if not meta.tasks:
        step.error(IssueCode.TASK_MISSING, "meta/tasks.parquet is empty", path="meta/tasks.parquet")
    known = set(meta.tasks)
    for e in meta.episodes:
        if not e.tasks:
            step.warn(IssueCode.TASK_MISSING, "Episode has no task", episode_index=e.index)
        elif any(t not in known for t in e.tasks):
            step.error(IssueCode.TASK_MISSING, "Episode references an unknown task", episode_index=e.index)


# --------------------------------------------------------------------------------------------------
# decode
# --------------------------------------------------------------------------------------------------
def _camera_hw(spec: dict[str, Any]) -> tuple[int, int] | None:
    shape = spec.get("shape")
    if not _valid_shape(shape) or len(shape) != 3:
        return None
    if spec.get("names") == ["channels", "height", "width"]:
        return int(shape[1]), int(shape[2])
    return int(shape[0]), int(shape[1])


def check_decode(meta: DatasetMeta, step: Step, progress: Progress = _noop) -> dict[str, dict[str, Any]]:
    """Decode first / middle / last frame of every episode of every video feature.

    Returns per video key ``{"codec", "width", "height"}`` (from the first readable file).
    """
    fps = meta.fps
    codecs: dict[str, dict[str, Any]] = {}
    keys = meta.video_keys
    total = max(1, len(keys) * len(meta.episodes))
    done = 0
    for key in keys:
        hw = _camera_hw(meta.features[key])
        by_file: dict[str, list[EpisodeMeta]] = {}
        for e in meta.episodes:
            ref = e.videos.get(key)
            if ref is not None:
                by_file.setdefault(meta.video_path(key, ref), []).append(e)
        for rel, eps in sorted(by_file.items()):
            path = meta.root / rel
            if not path.is_file():
                done += len(eps)
                continue  # reported by structure
            try:
                vinfo = video.probe(path)
            except video.DecodeError as exc:
                step.error(IssueCode.VIDEO_DECODE_FAILED, f"Cannot open video: {exc}", path=rel, feature=key)
                done += len(eps)
                progress(done / total)
                continue
            codecs.setdefault(key, {"codec": vinfo.codec, "width": vinfo.width, "height": vinfo.height})
            if hw is not None and (vinfo.height, vinfo.width) != hw:
                step.error(
                    IssueCode.CAMERA_SHAPE_MISMATCH,
                    "Decoded video size differs from the feature shape",
                    path=rel,
                    feature=key,
                    params={"expected": list(hw), "actual": [vinfo.height, vinfo.width]},
                )
            for e in eps:
                ref = e.videos[key]
                n_expected = video.expected_frames(ref.from_timestamp, ref.to_timestamp, fps)
                if abs(n_expected - e.length) > 1:
                    step.error(
                        IssueCode.FRAME_COUNT_MISMATCH,
                        "Video segment length differs from the episode length",
                        episode_index=e.index,
                        feature=key,
                        path=rel,
                        params={"video_frames": n_expected, "episode_length": e.length},
                    )
                if vinfo.duration_s is not None and ref.to_timestamp > vinfo.duration_s + 1.0 / fps + 1e-3:
                    step.error(
                        IssueCode.VIDEO_DECODE_FAILED,
                        "Episode extends beyond the end of the video file",
                        episode_index=e.index,
                        feature=key,
                        path=rel,
                        params={
                            "to_timestamp": ref.to_timestamp,
                            "video_duration_s": round(vinfo.duration_s, 4),
                        },
                    )
                    done += 1
                    continue
                last = max(e.length - 1, 0)
                frame_idx = sorted({0, last // 2, last})
                ts = [ref.from_timestamp + i / fps for i in frame_idx]
                try:
                    results = video.decode_at(path, ts, fps)
                except video.DecodeError as exc:
                    step.error(
                        IssueCode.VIDEO_DECODE_FAILED,
                        f"Decode failed: {exc}",
                        episode_index=e.index,
                        path=rel,
                    )
                    done += 1
                    continue
                failed = [fi for fi, r in zip(frame_idx, results, strict=True) if r is None]
                if failed:
                    step.error(
                        IssueCode.VIDEO_DECODE_FAILED,
                        "Frame(s) could not be decoded",
                        episode_index=e.index,
                        feature=key,
                        path=rel,
                        params={"frames": failed},
                    )
                done += 1
                progress(done / total)
    return codecs


# --------------------------------------------------------------------------------------------------
# timestamps (+ NaN) and stats (shared single pass over the data files)
# --------------------------------------------------------------------------------------------------
@dataclass(slots=True)
class _Acc:
    n: int = 0
    mean: FloatArray | None = None
    m2: FloatArray | None = None
    vmin: FloatArray | None = None
    vmax: FloatArray | None = None

    def update(self, x: FloatArray) -> None:
        if x.shape[0] == 0:
            return
        bn = x.shape[0]
        bmean = x.mean(axis=0)
        bm2 = ((x - bmean) ** 2).sum(axis=0)
        bmin, bmax = x.min(axis=0), x.max(axis=0)
        if self.mean is None or self.m2 is None or self.vmin is None or self.vmax is None:
            self.n, self.mean, self.m2, self.vmin, self.vmax = bn, bmean, bm2, bmin, bmax
            return
        tot = self.n + bn
        delta = bmean - self.mean
        self.mean = self.mean + delta * (bn / tot)
        self.m2 = self.m2 + bm2 + delta**2 * (self.n * bn / tot)
        self.vmin = np.minimum(self.vmin, bmin)
        self.vmax = np.maximum(self.vmax, bmax)
        self.n = tot

    def result(self) -> dict[str, FloatArray] | None:
        if self.mean is None or self.m2 is None or self.vmin is None or self.vmax is None or self.n == 0:
            return None
        return {"mean": self.mean, "std": np.sqrt(self.m2 / self.n), "min": self.vmin, "max": self.vmax}


def _column_2d(table: pa.Table, key: str) -> FloatArray:
    col = table.column(key).combine_chunks()
    if pa.types.is_fixed_size_list(col.type):
        width = col.type.list_size
        flat = col.flatten().to_numpy(zero_copy_only=False)
        return np.asarray(flat, dtype=np.float64).reshape(-1, width)
    if pa.types.is_list(col.type) or pa.types.is_large_list(col.type):
        return np.asarray(col.to_pylist(), dtype=np.float64)
    return np.asarray(col.to_numpy(zero_copy_only=False), dtype=np.float64).reshape(-1, 1)


@dataclass(slots=True)
class DataScan:
    stats: dict[str, dict[str, FloatArray]] = field(default_factory=dict)
    series: dict[int, dict[str, FloatArray]] = field(default_factory=dict)  # episode -> feature -> (T, D)
    timestamps: dict[int, FloatArray] = field(default_factory=dict)


SERIES_FEATURES = ("observation.state", "action")


def check_timestamps(
    meta: DatasetMeta, step: Step, progress: Progress = _noop, keep_series: bool = True
) -> DataScan:
    """Timestamps regular and consistent with fps, frame/index columns consistent, no NaN/Inf.

    Also accumulates exact (population) statistics for the stats step and per-episode series for
    the preview, so the data files are read only once.
    """
    fps = meta.fps
    period = 1.0 / fps
    feats = meta.features
    numeric = [
        k
        for k, v in feats.items()
        if isinstance(v, dict) and v.get("dtype") not in VISUAL_DTYPES and v.get("dtype") != "string"
    ]
    accs: dict[str, _Acc] = {k: _Acc() for k in numeric}
    scan = DataScan()
    files = meta.data_files()
    eps_by_file: dict[tuple[int, int], list[EpisodeMeta]] = {}
    for e in meta.episodes:
        eps_by_file.setdefault((e.data_chunk, e.data_file), []).append(e)
    for fi, (chunk, file) in enumerate(files):
        rel = meta.data_path(chunk, file)
        p = meta.root / rel
        if not p.is_file():
            continue
        try:
            names = pq.read_schema(p).names
            cols = [k for k in numeric if k in names]
            table = pq.read_table(p, columns=cols)
        except (pa.ArrowException, OSError) as exc:
            step.error(IssueCode.MISSING_FILE, f"Data file unreadable: {exc}", path=rel)
            continue
        arrays = {k: _column_2d(table, k) for k in cols}
        for k, arr in arrays.items():
            bad = ~np.isfinite(arr)
            if bad.any():
                rows = np.nonzero(bad.any(axis=1))[0]
                ep_col = arrays.get("episode_index")
                eps = sorted({int(ep_col[r, 0]) for r in rows[:1000]}) if ep_col is not None else []
                step.error(
                    IssueCode.NAN_VALUES,
                    f"Non-finite values in '{k}'",
                    feature=k,
                    path=rel,
                    params={"count": int(bad.sum()), "episodes": eps[:50]},
                    episode_index=eps[0] if len(eps) == 1 else None,
                )
                arr = np.where(bad, np.nan, arr)
            finite_rows = np.isfinite(arr).all(axis=1)
            accs[k].update(arr[finite_rows])
        gidx = arrays.get("index")
        ts_all = arrays.get("timestamp")
        fidx = arrays.get("frame_index")
        epc = arrays.get("episode_index")
        if gidx is None or ts_all is None or fidx is None or epc is None:
            continue  # reported by schema
        base = int(gidx[0, 0]) if gidx.shape[0] else 0
        for e in eps_by_file.get((chunk, file), []):
            lo, hi = e.from_index - base, e.to_index - base
            if lo < 0 or hi > gidx.shape[0] or hi - lo != e.length:
                step.error(
                    IssueCode.FRAME_COUNT_MISMATCH,
                    "Episode row range does not match its data file",
                    episode_index=e.index,
                    path=rel,
                    params={"from": e.from_index, "to": e.to_index, "length": e.length},
                )
                continue
            if e.length < MIN_EPISODE_FRAMES:
                step.error(
                    IssueCode.EPISODE_TOO_SHORT, "Episode has fewer than 2 frames", episode_index=e.index
                )
            elif e.length < fps:
                step.warn(
                    IssueCode.EPISODE_TOO_SHORT,
                    "Episode is shorter than one second",
                    episode_index=e.index,
                    params={"length": e.length},
                )
            ts = ts_all[lo:hi, 0]
            if not np.array_equal(epc[lo:hi, 0], np.full(e.length, e.index)):
                step.error(
                    IssueCode.FRAME_COUNT_MISMATCH, "episode_index column mismatch", episode_index=e.index
                )
            if not np.array_equal(fidx[lo:hi, 0], np.arange(e.length)):
                step.error(
                    IssueCode.FRAME_COUNT_MISMATCH, "frame_index is not 0..length-1", episode_index=e.index
                )
            if not np.array_equal(gidx[lo:hi, 0], np.arange(e.from_index, e.to_index)):
                step.error(
                    IssueCode.FRAME_COUNT_MISMATCH, "index column is not contiguous", episode_index=e.index
                )
            if np.isfinite(ts).all() and ts.shape[0] >= 2:
                diffs = np.diff(ts)
                med = float(np.median(diffs))
                if abs(med - period) > TIMESTAMP_TOLERANCE_S:
                    step.error(
                        IssueCode.TIMESTAMP_FPS_MISMATCH,
                        "Timestamp spacing does not match fps",
                        episode_index=e.index,
                        params={
                            "fps": fps,
                            "median_dt": round(med, 6),
                            "implied_fps": round(1.0 / med, 3) if med > 0 else None,
                        },
                    )
                else:
                    off = np.abs(diffs - period) > TIMESTAMP_TOLERANCE_S
                    if off.any():
                        first = int(np.nonzero(off)[0][0])
                        step.error(
                            IssueCode.TIMESTAMP_IRREGULAR,
                            "Irregular timestamps",
                            episode_index=e.index,
                            params={
                                "count": int(off.sum()),
                                "first_frame": first + 1,
                                "max_abs_dev_s": round(float(np.abs(diffs - period).max()), 6),
                            },
                        )
                if abs(float(ts[0])) > TIMESTAMP_TOLERANCE_S:
                    step.warn(
                        IssueCode.TIMESTAMP_IRREGULAR,
                        "Episode timestamps do not start at 0",
                        episode_index=e.index,
                        params={"first": float(ts[0])},
                    )
            if keep_series:
                scan.timestamps[e.index] = ts.astype(np.float64)
                scan.series[e.index] = {k: arrays[k][lo:hi] for k in SERIES_FEATURES if k in arrays}
        progress((fi + 1) / max(1, len(files)))
    for k, acc in accs.items():
        r = acc.result()
        if r is not None:
            scan.stats[k] = r
    return scan


def _rel_diff(a: FloatArray, b: FloatArray, scale: FloatArray) -> float:
    denom = np.maximum(np.maximum(np.abs(b), scale), 1e-6)
    return float(np.max(np.abs(a - b) / denom)) if a.size else 0.0


def check_stats(
    meta: DatasetMeta, stats: dict[str, Any] | None, scan: DataScan, step: Step
) -> dict[str, dict[str, float]]:
    """Compare recomputed mean/std/min/max with meta/stats.json. Returns max relative differences."""
    out: dict[str, dict[str, float]] = {}
    if stats is None:
        step.error(IssueCode.STATS_MISSING, "meta/stats.json missing or invalid", path="meta/stats.json")
        return out
    for key in ("action", "observation.state", *meta.camera_keys):
        if key in meta.features and key not in stats:
            step.error(IssueCode.STATS_MISSING, f"stats.json has no entry for '{key}'", feature=key)
    for key, rec in scan.stats.items():
        ref = stats.get(key)
        if not isinstance(ref, dict):
            continue
        diffs: dict[str, float] = {}
        for stat in ("mean", "std", "min", "max"):
            if stat not in ref:
                step.error(IssueCode.STATS_MISSING, f"stats.json '{key}' lacks '{stat}'", feature=key)
                continue
            try:
                stored = np.asarray(ref[stat], dtype=np.float64).reshape(-1)
            except (TypeError, ValueError):
                step.error(IssueCode.STATS_MISSING, f"stats.json '{key}.{stat}' is not numeric", feature=key)
                continue
            mine = rec[stat].reshape(-1)
            if stored.shape != mine.shape:
                step.error(
                    IssueCode.STATS_MISMATCH,
                    f"stats.json '{key}.{stat}' has the wrong shape",
                    feature=key,
                    params={"expected": list(mine.shape), "actual": list(stored.shape)},
                )
                continue
            diffs[stat] = round(_rel_diff(mine, stored, rec["std"].reshape(-1)), 8)
        out[key] = diffs
        worst = max(diffs.values(), default=0.0)
        # Index-like columns are never normalised by LeRobot (and its own merge leaves their stats
        # stale), so they are reported in the diff table but never raise an issue.
        if worst > STATS_WARN_REL_DIFF and key not in INDEX_FEATURES:
            step.warn(
                IssueCode.STATS_MISMATCH,
                f"Recomputed stats for '{key}' differ from stats.json",
                feature=key,
                params={"max_rel_diff": worst, "threshold": STATS_WARN_REL_DIFF, **diffs},
            )
    for key in meta.camera_keys:
        ref = stats.get(key)
        if isinstance(ref, dict) and "mean" in ref:
            try:
                shape = list(np.asarray(ref["mean"], dtype=np.float64).shape)
            except (TypeError, ValueError):
                shape = []
            if shape != [3, 1, 1]:
                step.warn(
                    IssueCode.STATS_MISMATCH,
                    "Camera stats should have shape [3, 1, 1]",
                    feature=key,
                    params={"shape": shape},
                )
    return out


def episode_series_json(
    meta: DatasetMeta, ep: EpisodeMeta, scan: DataScan, max_points: int = 5000
) -> tuple[list[float], list[dict[str, Any]]]:
    ts = scan.timestamps.get(ep.index)
    series = scan.series.get(ep.index, {})
    if ts is None:
        return [], []
    n = ts.shape[0]
    idx = (
        np.arange(n) if n <= max_points else np.unique(np.linspace(0, n - 1, max_points).round().astype(int))
    )
    out_series: list[dict[str, Any]] = []
    for key in SERIES_FEATURES:
        arr = series.get(key)
        if arr is None:
            continue
        spec = meta.features.get(key, {})
        names = _names_list(spec) if isinstance(spec, dict) else None
        for d in range(arr.shape[1]):
            col = arr[idx, d]
            out_series.append(
                {
                    "feature": key,
                    "dim": d,
                    "name": names[d] if names and d < len(names) else f"{key}[{d}]",
                    "values": [None if not math.isfinite(v) else round(float(v), 6) for v in col],
                }
            )
    return [round(float(t), 6) for t in ts[idx]], out_series


def numpy_stats_to_json(stats: dict[str, dict[str, FloatArray]]) -> dict[str, dict[str, list[float]]]:
    return {k: {s: [float(x) for x in v.reshape(-1)] for s, v in d.items()} for k, d in stats.items()}


def relpath(root: Path, p: Path) -> str:
    return p.relative_to(root).as_posix()
