"""Golden end-to-end: the REAL RAR5 archive collected on the robot (PLAN 6 "Golden E2E", data half).

unpack (libarchive, sandboxed) -> 7 validation steps all green -> 20 H.264 previews + thumbnails.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import av
import pytest

from validate.hashing import hash_tree
from validate.pipeline import PipelineInput, run_pipeline
from validate.tests.conftest import GOLDEN_DIR

CAM = "observation.images.wrist_cam"


def test_golden_rar_end_to_end(golden_rar: Path, tmp_path: Path) -> None:
    sha = hashlib.sha256(golden_rar.read_bytes()).hexdigest()
    seen: list[str] = []
    out = run_pipeline(
        PipelineInput(
            "11111111-1111-4111-8111-111111111111", tmp_path / "work", archive=golden_rar, expected_sha256=sha
        ),
        lambda stage, _f: seen.append(str(stage)) if not seen or seen[-1] != str(stage) else None,
    )
    rep = out.report.to_json()
    assert out.status == "ready", json.dumps(rep, indent=1)[:4000]
    assert rep["summary"] == {"result": "passed", "errors": 0, "warnings": 0}
    assert [s["id"] for s in rep["steps"]] == [
        "checksum",
        "unpack",
        "structure",
        "schema",
        "decode",
        "timestamps",
        "stats",
    ]
    assert all(s["status"] == "passed" for s in rep["steps"]), [(s["id"], s["status"]) for s in rep["steps"]]
    assert out.fields["unpack"]["format"] == "rar5"
    assert out.fields["total_episodes"] == 20 and out.fields["total_frames"] == 11277
    assert out.fields["fps"] == 30 and out.fields["robot_type"] == "so_follower"
    assert out.fields["camera_keys"] == [CAM]
    assert out.fields["codebase_version"] == "v3.0" and "converted_from" not in out.fields
    assert len(out.fields["joint_names"]) == 6
    assert seen[:2] == ["checksum", "unpack"] and "preview" in seen

    # The archive holds exactly the dataset of the golden directory: identical content hash.
    if GOLDEN_DIR.is_dir():
        assert out.content_hash == hash_tree(GOLDEN_DIR)[0]
    assert out.size_bytes == 148111356

    # Previews for every episode: H.264, <= 480p, frame count == episode length, JPEG thumbnail.
    assert out.preview is not None and out.derived_dir is not None
    lengths = {e["index"]: e["length"] for e in out.preview["episodes"]}
    assert len(lengths) == 20 and sum(lengths.values()) == 11277
    for idx, length in lengths.items():
        mp4 = out.derived_dir / "previews" / CAM / f"episode_{idx:06d}.mp4"
        jpg = out.derived_dir / "previews" / CAM / f"episode_{idx:06d}.jpg"
        assert jpg.stat().st_size > 1000 and jpg.read_bytes()[:3] == b"\xff\xd8\xff"
        with av.open(str(mp4)) as c:
            s = c.streams.video[0]
            assert s.codec_context.name == "h264"
            assert (s.codec_context.width, s.codec_context.height) == (640, 360)
            n = sum(1 for _ in c.decode(s))
        assert n == length, (idx, n, length)
        detail = json.loads((out.derived_dir / "episodes" / f"episode_{idx:06d}.json").read_text())
        assert detail["videos"][0]["codec"] == "av1"
        assert detail["videos"][0]["browser_playable_hint"] is False
        assert detail["videos"][0]["media_path"] == f"videos/{CAM}/chunk-000/file-000.mp4"
        assert len(detail["timestamps"]) == length
    assert out.preview["episodes"][0]["thumbnails"] == {CAM: f"previews/{CAM}/episode_000000.jpg"}


@pytest.mark.parametrize("bad_sha", ["f" * 64])
def test_golden_rar_checksum_mismatch(golden_rar: Path, tmp_path: Path, bad_sha: str) -> None:
    out = run_pipeline(PipelineInput("x", tmp_path / "w", archive=golden_rar, expected_sha256=bad_sha))
    assert out.status == "failed" and out.error_code == "upload_checksum_mismatch"
