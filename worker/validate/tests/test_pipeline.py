"""Validation pipeline on real (synthetic but genuine) LeRobot datasets, incl. corrupted ones."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import av
import libarchive
import numpy as np
import pyarrow as pa  # type: ignore[import-untyped]  # pyarrow ships no type information
import pyarrow.parquet as pq  # type: ignore[import-untyped]  # pyarrow ships no type information
import pytest

from validate.archive import UnpackLimits
from validate.hashing import hash_tree
from validate.pipeline import PipelineInput, PipelineOutput, run_pipeline
from validate.tests.synth import CAM, SynthSpec, make_v21

VID = "00000000-0000-4000-8000-000000000001"


def run_dir(ds_parent: Path, tmp_path: Path, **kw: Any) -> PipelineOutput:
    return run_pipeline(PipelineInput(VID, tmp_path / "work", dataset_dir=ds_parent, **kw))


def codes(out: PipelineOutput, step: str | None = None) -> set[str]:
    rep = out.report.to_json()
    return {i["code"] for s in rep["steps"] if step is None or s["id"] == step for i in s["issues"]}


def step_status(out: PipelineOutput) -> dict[str, str]:
    return {s["id"]: s["status"] for s in out.report.to_json()["steps"]}


def rewrite_info(ds: Path, fn: Callable[[dict[str, Any]], None]) -> None:
    p = ds / "meta" / "info.json"
    info = json.loads(p.read_text())
    fn(info)
    p.write_text(json.dumps(info))


def rewrite_data(ds: Path, fn: Callable[[dict[str, Any]], None]) -> None:
    p = ds / "data" / "chunk-000" / "file-000.parquet"
    cols = pq.read_table(p).to_pydict()
    fn(cols)
    tbl = pa.table(
        {
            k: pa.FixedSizeListArray.from_arrays(pa.array(np.asarray(v, dtype=np.float32).reshape(-1)), 6)
            if k in ("action", "observation.state")
            else (pa.array(np.asarray(v, dtype=np.float32)) if k == "timestamp" else pa.array(v))
            for k, v in cols.items()
        }
    )
    pq.write_table(tbl, p)


# --------------------------------------------------------------------------------------------------
def test_valid_dataset_all_green_with_previews(synth_ds: Path, tmp_path: Path) -> None:
    out = run_dir(synth_ds.parent, tmp_path)
    rep = out.report.to_json()
    assert out.status == "ready", rep
    assert rep["summary"] == {"result": "passed", "errors": 0, "warnings": 0}
    assert step_status(out) == {
        "checksum": "skipped",
        "unpack": "skipped",
        "structure": "passed",
        "schema": "passed",
        "decode": "passed",
        "timestamps": "passed",
        "stats": "passed",
    }
    assert len(rep["steps"]) == 7
    assert out.fields["total_episodes"] == 3 and out.fields["total_frames"] == 120
    assert out.fields["camera_keys"] == [CAM]
    assert out.fields["joint_names"][0] == "shoulder_pan.pos"
    assert all(v <= 1e-6 for d in rep["recomputed_stats_max_rel_diff"].values() for v in d.values())
    # content hash is the documented formula over the dataset root only
    h = hashlib.sha256()
    for p in sorted(
        (p for p in synth_ds.rglob("*") if p.is_file()), key=lambda p: p.relative_to(synth_ds).as_posix()
    ):
        h.update(
            p.relative_to(synth_ds).as_posix().encode()
            + b"\0"
            + hashlib.sha256(p.read_bytes()).hexdigest().encode()
            + b"\n"
        )
    assert out.content_hash == h.hexdigest()
    # previews: H.264, <= 480p, one per episode, frame count == episode length, first-frame JPEG
    assert out.derived_dir is not None and out.preview is not None
    for e in range(3):
        mp4 = out.derived_dir / "previews" / CAM / f"episode_{e:06d}.mp4"
        jpg = out.derived_dir / "previews" / CAM / f"episode_{e:06d}.jpg"
        assert jpg.read_bytes()[:3] == b"\xff\xd8\xff"
        with av.open(str(mp4)) as c:
            s = c.streams.video[0]
            assert s.codec_context.name == "h264"
            assert s.codec_context.height <= 480
            assert sum(1 for _ in c.decode(s)) == 40
        detail = json.loads((out.derived_dir / "episodes" / f"episode_{e:06d}.json").read_text())
        assert detail["length"] == 40 and len(detail["timestamps"]) == 40
        assert {s["feature"] for s in detail["series"]} == {"observation.state", "action"}
        assert len(detail["series"]) == 12
        v = detail["videos"][0]
        assert v["preview_media_path"] == f"previews/{CAM}/episode_{e:06d}.mp4"
        assert v["codec"] == "h264" and v["browser_playable_hint"] is True
    assert [ep["thumbnails"][CAM] for ep in out.preview["episodes"]] == [
        f"previews/{CAM}/episode_{e:06d}.jpg" for e in range(3)
    ]
    assert sum(out.preview["length_histogram"]["counts"]) == 3


def _pack(src_parent: Path, arc: Path, fmt: str, filt: str | None) -> None:
    cwd = os.getcwd()
    os.chdir(src_parent)
    try:
        with libarchive.file_writer(str(arc), fmt, filt) as w:
            w.add_files("my_dataset")
    finally:
        os.chdir(cwd)


@pytest.mark.parametrize(
    ("fmt", "filt", "ext"), [("zip", None, "zip"), ("pax", "zstd", "tar.zst"), ("pax", "gzip", "tar.gz")]
)
def test_archive_end_to_end(synth_ds: Path, tmp_path: Path, fmt: str, filt: str | None, ext: str) -> None:
    arc = tmp_path / f"upload.{ext}"
    _pack(synth_ds.parent, arc, fmt, filt)
    sha = hashlib.sha256(arc.read_bytes()).hexdigest()
    out = run_pipeline(PipelineInput(VID, tmp_path / "work", archive=arc, expected_sha256=sha))
    assert out.status == "ready", out.report.to_json()
    assert step_status(out)["checksum"] == "passed" and step_status(out)["unpack"] == "passed"
    assert out.content_hash == hash_tree(synth_ds)[0]


def test_checksum_mismatch_fails_version(synth_ds: Path, tmp_path: Path) -> None:
    arc = tmp_path / "u.tar"
    with tarfile.open(arc, "w") as tf:
        tf.add(synth_ds, arcname="my_dataset")
    out = run_pipeline(PipelineInput(VID, tmp_path / "work", archive=arc, expected_sha256="0" * 64))
    assert out.status == "failed" and out.error_code == "upload_checksum_mismatch"
    assert codes(out, "checksum") == {"checksum_mismatch"}
    assert step_status(out)["unpack"] == "skipped"


def test_unsafe_archive_makes_version_invalid(tmp_path: Path) -> None:
    arc = tmp_path / "evil.tar"
    with tarfile.open(arc, "w") as tf:
        ti = tarfile.TarInfo("my_dataset/meta")
        ti.type = tarfile.SYMTYPE
        ti.linkname = "/"
        tf.addfile(ti)
    out = run_pipeline(PipelineInput(VID, tmp_path / "work", archive=arc))
    assert out.status == "invalid"
    assert codes(out, "unpack") == {"archive_symlink"}
    assert step_status(out)["structure"] == "skipped"


def test_zip_bomb_in_pipeline(tmp_path: Path) -> None:
    import zipfile

    arc = tmp_path / "bomb.zip"
    with (
        zipfile.ZipFile(arc, "w", compression=zipfile.ZIP_DEFLATED) as zf,
        zf.open("ds/meta/x.bin", "w") as fh,
    ):
        for _ in range(64):
            fh.write(b"\0" * (1024 * 1024))
    limits = UnpackLimits(max_ratio=50, ratio_floor_bytes=4 * 1024 * 1024)
    out = run_pipeline(PipelineInput(VID, tmp_path / "work", archive=arc, limits=limits))
    assert out.status == "invalid" and codes(out, "unpack") == {"archive_bomb"}


def test_no_root_and_multiple_roots(synth_ds: Path, tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    (empty / "x").mkdir(parents=True)
    out = run_pipeline(PipelineInput(VID, tmp_path / "w1", dataset_dir=empty))
    assert out.status == "invalid" and codes(out) == {"dataset_root_not_found"}
    shutil.copytree(synth_ds, synth_ds.parent / "second")
    out = run_dir(synth_ds.parent, tmp_path / "w2")
    assert codes(out) == {"multiple_dataset_roots"}


def test_wrong_schema(synth_ds: Path, tmp_path: Path) -> None:
    def mutate(info: dict[str, Any]) -> None:
        del info["features"]["action"]
        info["features"]["observation.state"]["names"] = ["a", "b"]
        info["features"][CAM]["info"]["video.width"] = 999

    rewrite_info(synth_ds, mutate)
    out = run_dir(synth_ds.parent, tmp_path)
    assert out.status == "invalid"
    c = codes(out, "schema")
    assert {"feature_missing", "joint_names_mismatch", "camera_shape_mismatch"} <= c
    assert step_status(out)["schema"] == "failed"


def test_bad_info_json_and_unsupported_version(synth_ds: Path, tmp_path: Path) -> None:
    (synth_ds / "meta" / "info.json").write_text("{not json")
    out = run_dir(synth_ds.parent, tmp_path / "a")
    assert codes(out) == {"info_json_invalid"} and out.status == "invalid"
    (synth_ds / "meta" / "info.json").write_text(
        json.dumps({"codebase_version": "v1.6", "fps": 30, "features": {"a": {}}})
    )
    out = run_dir(synth_ds.parent, tmp_path / "b")
    assert codes(out) == {"unsupported_codebase_version"}


def test_missing_files(synth_ds: Path, tmp_path: Path) -> None:
    (synth_ds / "videos" / CAM / "chunk-000" / "file-000.mp4").unlink()
    (synth_ds / "meta" / "stats.json").unlink()
    out = run_dir(synth_ds.parent, tmp_path)
    assert "video_missing" in codes(out, "structure")
    assert "stats_missing" in codes(out, "stats")
    assert out.status == "invalid"


def test_truncated_video(synth_ds: Path, tmp_path: Path) -> None:
    mp4 = synth_ds / "videos" / CAM / "chunk-000" / "file-000.mp4"
    data = mp4.read_bytes()
    mp4.write_bytes(data[: len(data) // 2])
    out = run_dir(synth_ds.parent, tmp_path)
    assert out.status == "invalid"
    assert "video_decode_failed" in codes(out, "decode")
    assert step_status(out)["decode"] == "failed"


def test_video_shorter_than_episodes(synth_ds: Path, tmp_path: Path) -> None:
    """A valid but too-short mp4 (2 of 3 episodes): last episode cannot be decoded."""
    from validate.tests.synth import _encode_video, _frames

    mp4 = synth_ds / "videos" / CAM / "chunk-000" / "file-000.mp4"
    spec = SynthSpec()
    _encode_video(mp4, np.concatenate([_frames(spec, 0), _frames(spec, 1)]), 30)
    out = run_dir(synth_ds.parent, tmp_path)
    issues = [
        i for s in out.report.to_json()["steps"] for i in s["issues"] if i["code"] == "video_decode_failed"
    ]
    assert issues and all(i["episode_index"] == 2 for i in issues)
    ep2 = next(e for e in (out.preview or {})["episodes"] if e["index"] == 2)
    assert ep2["has_issues"] is True


def test_nan_and_timestamp_problems(synth_ds: Path, tmp_path: Path) -> None:
    def mutate(cols: dict[str, Any]) -> None:
        cols["action"][5][2] = float("nan")
        ts = cols["timestamp"]
        ts[45] = ts[45] + 0.02  # episode 1 frame 5 jitters

    rewrite_data(synth_ds, mutate)
    out = run_dir(synth_ds.parent, tmp_path)
    c = codes(out, "timestamps")
    assert {"nan_values", "timestamp_irregular"} <= c
    nan = next(i for i in out.report.to_json()["steps"][5]["issues"] if i["code"] == "nan_values")
    assert nan["episode_index"] == 0 and nan["feature"] == "action"
    assert out.status == "invalid"


def test_fps_mismatch(synth_ds: Path, tmp_path: Path) -> None:
    rewrite_info(synth_ds, lambda info: info.update(fps=15))
    out = run_dir(synth_ds.parent, tmp_path)
    assert "timestamp_fps_mismatch" in codes(out, "timestamps")


def test_frame_index_and_episode_count(synth_ds: Path, tmp_path: Path) -> None:
    rewrite_info(synth_ds, lambda info: info.update(total_frames=999))
    out = run_dir(synth_ds.parent, tmp_path)
    assert "frame_count_mismatch" in codes(out, "structure")


def test_stats_mismatch_is_warning(synth_ds: Path, tmp_path: Path) -> None:
    p = synth_ds / "meta" / "stats.json"
    stats = json.loads(p.read_text())
    stats["action"]["mean"] = [m + 5.0 for m in stats["action"]["mean"]]
    p.write_text(json.dumps(stats))
    out = run_dir(synth_ds.parent, tmp_path)
    assert out.status == "ready"
    assert codes(out, "stats") == {"stats_mismatch"}
    assert step_status(out)["stats"] == "warning"
    assert out.report.to_json()["summary"]["result"] == "passed_with_warnings"
    assert out.report.recomputed_stats_max_rel_diff is not None
    assert out.report.recomputed_stats_max_rel_diff["action"]["mean"] > 0.01


def test_unknown_task_reference(synth_ds: Path, tmp_path: Path) -> None:
    from validate.tests.synth import write_tasks

    write_tasks(synth_ds, ["other"])
    out = run_dir(synth_ds.parent, tmp_path)
    assert "task_missing" in codes(out, "schema")


def test_v21_is_converted_with_lerobot(tmp_path: Path) -> None:
    make_v21(tmp_path / "src" / "old_ds", SynthSpec(episodes=2, length=30))
    out = run_dir(tmp_path / "src", tmp_path)
    assert out.status == "ready", out.report.to_json()
    assert out.fields["converted_from"] == "v2.1"
    assert out.fields["codebase_version"] == "v3.0"
    root = tmp_path / "src" / "old_ds"
    assert (root / "meta" / "episodes").is_dir() and not (root / "meta" / "episodes.jsonl").exists()
    assert not (tmp_path / "src" / "old_ds_old").exists()
    assert out.fields["total_frames"] == 60


def test_report_caps_issues_at_500(synth_ds: Path, tmp_path: Path) -> None:
    from validate.report import IssueCode, Report, StepId

    r = Report(VID, None, "x")
    with r.run(StepId.STATS) as st:
        for _ in range(650):
            st.warn(IssueCode.STATS_MISMATCH, "x")
    j = r.to_json()["steps"][6]
    assert len(j["issues"]) == 500 and j["issues_truncated"] == 150 and j["status"] == "warning"


def test_tasks_with_unnamed_pandas_index(synth_ds: Path, tmp_path: Path) -> None:
    """Older LeRobot writers (e.g. lerobot/pusht) store the task string as ``__index_level_0__``."""
    import pandas as pd  # type: ignore[import-untyped]  # pandas-stubs not installed

    from validate.tests.synth import TASK

    pd.DataFrame({"task_index": [0]}, index=[TASK]).to_parquet(synth_ds / "meta" / "tasks.parquet")
    assert "__index_level_0__" in pq.read_schema(synth_ds / "meta" / "tasks.parquet").names
    out = run_dir(synth_ds.parent, tmp_path)
    assert out.status == "ready", out.report.to_json()
    assert out.fields["tasks"] == [TASK]


def test_runner_helpers() -> None:
    import base64

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    from validate.runner import JobError, decrypt_secret, parse_hf_uri

    assert parse_hf_uri("hf://lerobot/pusht@main") == ("lerobot/pusht", "main")
    assert parse_hf_uri("hf://org/name") == ("org/name", None)
    for bad in ("hf://a/b/../c", "https://x/y", "hf://a"):
        with pytest.raises(JobError):
            parse_hf_uri(bad)
    key = os.urandom(32)
    nonce = os.urandom(12)
    blob = nonce + AESGCM(key).encrypt(nonce, b"hf_secret", None)
    assert decrypt_secret(base64.b64encode(key).decode(), blob) == "hf_secret"
