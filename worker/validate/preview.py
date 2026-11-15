"""Derived preview artefacts of a dataset version (never part of the content hash).

Output tree (``derived/``), uploaded to ``s3://hibiscus-datasets/<ws>/<ds>/<ver>.derived/``::

    previews/<camera_key>/episode_000003.mp4   H.264 <= 480p, CRF 28, starts at t=0
    previews/<camera_key>/episode_000003.jpg   first frame
    episodes/episode_000003.json               EpisodeDetail (full-rate series, <= 5000 points)
    manifest.json                              dataset files (path, size, sha256) + content hash

``DatasetPreview`` (OpenAPI) is returned for ``dataset_versions.preview``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from validate import video
from validate.checks import DataScan, episode_series_json
from validate.lerobot_meta import DatasetMeta, EpisodeMeta
from validate.report import IssueCode, Step

BROWSER_PLAYABLE_CODECS = {"h264", "libx264", "vp8", "vp9", "libvpx-vp9"}


def preview_clip_path(camera_key: str, episode_index: int) -> str:
    return f"previews/{camera_key}/episode_{episode_index:06d}.mp4"


def thumbnail_path(camera_key: str, episode_index: int) -> str:
    return f"previews/{camera_key}/episode_{episode_index:06d}.jpg"


def episode_json_path(episode_index: int) -> str:
    return f"episodes/episode_{episode_index:06d}.json"


@dataclass(slots=True)
class PreviewResult:
    preview: dict[str, Any]
    clips: dict[tuple[str, int], int] = field(default_factory=dict)  # (camera, episode) -> frames
    failed: list[tuple[str, int]] = field(default_factory=list)


def _length_histogram(lengths_s: list[float], bins: int = 10) -> dict[str, list[Any]]:
    if not lengths_s:
        return {"bin_edges_s": [], "counts": []}
    lo, hi = min(lengths_s), max(lengths_s)
    if hi - lo < 1e-9:
        return {"bin_edges_s": [round(lo, 4), round(lo + 1.0, 4)], "counts": [len(lengths_s)]}
    counts, edges = np.histogram(np.asarray(lengths_s), bins=bins, range=(lo, hi))
    return {"bin_edges_s": [round(float(x), 4) for x in edges], "counts": [int(c) for c in counts]}


def build_previews(
    meta: DatasetMeta,
    scan: DataScan,
    codecs: dict[str, dict[str, Any]],
    out_dir: Path,
    dataset_version_id: str,
    step: Step,
    issue_episodes: set[int],
    progress: Callable[[float], None] | None = None,
) -> PreviewResult:
    fps = meta.fps
    out_dir.mkdir(parents=True, exist_ok=True)
    clips: dict[tuple[str, int], int] = {}
    failed: list[tuple[str, int]] = []
    keys = meta.video_keys
    for ki, key in enumerate(keys):
        by_file: dict[str, list[EpisodeMeta]] = {}
        for e in meta.episodes:
            ref = e.videos.get(key)
            if ref is not None:
                by_file.setdefault(meta.video_path(key, ref), []).append(e)
        for rel, eps in sorted(by_file.items()):
            src = meta.root / rel
            specs = [
                video.ClipSpec(
                    e.index,
                    e.videos[key].from_timestamp,
                    e.videos[key].to_timestamp,
                    out_dir / preview_clip_path(key, e.index),
                    out_dir / thumbnail_path(key, e.index),
                )
                for e in eps
            ]
            try:
                written = video.make_clips(src, specs, fps) if src.is_file() else {}
            except video.DecodeError as exc:
                written = {}
                step.warn(
                    IssueCode.VIDEO_DECODE_FAILED,
                    f"Preview generation failed: {exc}",
                    path=rel,
                    feature=key,
                    params={"stage": "preview"},
                )
            for e in eps:
                n = written.get(e.index, 0)
                if n > 0:
                    clips[(key, e.index)] = n
                else:
                    failed.append((key, e.index))
                    for p in (
                        out_dir / preview_clip_path(key, e.index),
                        out_dir / thumbnail_path(key, e.index),
                    ):
                        p.unlink(missing_ok=True)
        if progress is not None:
            progress((ki + 1) / max(1, len(keys)))

    episodes_json: list[dict[str, Any]] = []
    for e in meta.episodes:
        thumbs = {k: thumbnail_path(k, e.index) for k in keys if (k, e.index) in clips}
        episodes_json.append(
            {
                "index": e.index,
                "length": e.length,
                "duration_s": round(e.length / fps, 4),
                "tasks": e.tasks,
                "thumbnails": thumbs,
                "has_issues": e.index in issue_episodes,
            }
        )
        timestamps, series = episode_series_json(meta, e, scan)
        videos: list[dict[str, Any]] = []
        for k in keys:
            ref = e.videos.get(k)
            if ref is None:
                continue
            c = codecs.get(k) or {}
            spec = meta.features.get(k, {})
            vinfo = spec.get("info") if isinstance(spec, dict) else None
            codec = str(c.get("codec") or (vinfo or {}).get("video.codec") or "unknown")
            codec = "av1" if codec in ("libdav1d", "libaom-av1") else codec
            shape = spec.get("shape") if isinstance(spec, dict) else None
            height = int(c.get("height") or (shape[0] if shape else 0))
            width = int(c.get("width") or (shape[1] if shape else 0))
            has_clip = (k, e.index) in clips
            videos.append(
                {
                    "camera_key": k,
                    "media_path": meta.video_path(k, ref),
                    "from_timestamp_s": ref.from_timestamp,
                    "to_timestamp_s": ref.to_timestamp,
                    "codec": codec,
                    "width": width,
                    "height": height,
                    "browser_playable_hint": codec in BROWSER_PLAYABLE_CODECS,
                    "preview_media_path": preview_clip_path(k, e.index) if has_clip else None,
                    "thumbnail_media_path": thumbnail_path(k, e.index) if has_clip else None,
                }
            )
        detail = {
            "index": e.index,
            "length": e.length,
            "fps": fps,
            "timestamps": timestamps,
            "series": series,
            "videos": videos,
        }
        p = out_dir / episode_json_path(e.index)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(detail, separators=(",", ":")), encoding="utf-8")

    preview = {
        "dataset_version_id": dataset_version_id,
        "fps": fps,
        "camera_keys": meta.camera_keys,
        "episodes": episodes_json,
        "length_histogram": _length_histogram([e.length / fps for e in meta.episodes]),
    }
    return PreviewResult(preview=preview, clips=clips, failed=failed)
