"""Golden E2E (data half of PLAN 6): the REAL RAR5 archive goes through the public API in 64 MiB
parts, the real CPU worker (``python -m validate --once``, LeRobot 0.7.1 env) validates it, and the
API then serves the report, preview, episode series, media with Range, and the tar download.

Needs the worker interpreter (LeRobot + libarchive + PyAV): ``HIBISCUS_WORKER_PYTHON=/path/to/python``.
"""

from __future__ import annotations

import hashlib
import io
import os
import subprocess
import tarfile
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.datasets.conftest import REPO, Services, assert_contract

GOLDEN_RAR = Path(
    os.environ.get("HIBISCUS_GOLDEN_RAR", "~/lelab/Picknplace_20261114_221710.rar")
)
WORKER_PY = os.environ.get("HIBISCUS_WORKER_PYTHON")
CAM = "observation.images.wrist_cam"
MIB = 1024 * 1024

pytestmark = pytest.mark.skipif(
    not WORKER_PY or not GOLDEN_RAR.is_file(), reason="set HIBISCUS_WORKER_PYTHON and provide the golden RAR"
)


def _run_worker(services: Services, work: Path) -> None:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", str(work)),
        "HIBISCUS_DATABASE_URL": services.pg_url_sync,
        "HIBISCUS_S3_ENDPOINT_URL": services.s3_endpoint,
        "HIBISCUS_S3_ACCESS_KEY": services.s3_key,
        "HIBISCUS_S3_SECRET_KEY": services.s3_secret,
        "HIBISCUS_VALIDATE_WORK_DIR": str(work),
        "HF_HOME": str(work / "hf"),
        "PYTHONPATH": str(REPO / "worker"),
    }
    assert WORKER_PY is not None
    proc = subprocess.run(  # noqa: S603 - fixed argv
        [WORKER_PY, "-m", "validate", "--once"],
        env=env,
        cwd=str(REPO / "worker"),
        capture_output=True,
        timeout=900,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr.decode()[-3000:]


async def test_golden_rar_through_api_and_worker(
    client: httpx.AsyncClient, make_actor: Any, services: Services, tmp_path: Path
) -> None:
    a = await make_actor()
    data = GOLDEN_RAR.read_bytes()  # noqa: ASYNC240 - test setup, 145 MB local read
    sha = hashlib.sha256(data).hexdigest()
    r = await client.post(
        "/uploads",
        json={
            "workspace_id": str(a.workspace_id),
            "new_dataset_name": "Picknplace 20261114",
            "filename": GOLDEN_RAR.name,
            "size": len(data),
            "sha256": sha,
        },
        headers=a.h,
    )
    assert r.status_code == 201, r.text
    up = r.json()
    assert up["archive_format"] == "rar" and up["part_size"] == 64 * MIB and up["part_count"] == 3
    for n in range(1, up["part_count"] + 1):
        chunk = data[(n - 1) * up["part_size"] : n * up["part_size"]]
        pr = await client.put(
            f"/uploads/{up['id']}/parts/{n}",
            content=chunk,
            headers={**a.h, "X-Content-SHA256": hashlib.sha256(chunk).hexdigest()},
        )
        assert pr.status_code == 200, pr.text
    done = await client.post(f"/uploads/{up['id']}/complete", headers=a.h)
    assert done.status_code == 202, done.text
    vid = done.json()["version"]["id"]

    _run_worker(services, tmp_path / "work")

    v = await client.get(f"/dataset-versions/{vid}", headers=a.h)
    assert_contract(v, "/dataset-versions/{version_id}")
    vb = v.json()
    assert vb["status"] == "ready", vb
    assert vb["validation_summary"] == {"result": "passed", "errors": 0, "warnings": 0}
    assert vb["total_episodes"] == 20 and vb["total_frames"] == 11277 and vb["fps"] == 30
    assert vb["camera_keys"] == [CAM] and vb["state_dim"] == 6 and vb["action_dim"] == 6
    assert vb["tasks"] == ["Pick the blue cube and place on top the white cube"]
    assert vb["error_code"] is None

    rep = await client.get(f"/dataset-versions/{vid}/validation", headers=a.h)
    assert_contract(rep, "/dataset-versions/{version_id}/validation")
    assert [s["status"] for s in rep.json()["steps"]] == ["passed"] * 7

    pv = await client.get(f"/dataset-versions/{vid}/preview", headers=a.h)
    assert_contract(pv, "/dataset-versions/{version_id}/preview")
    eps = pv.json()["episodes"]
    assert len(eps) == 20 and eps[0]["thumbnails"][CAM] == f"previews/{CAM}/episode_000000.jpg"

    ep = await client.get(f"/dataset-versions/{vid}/episodes/3", params={"max_points": 100}, headers=a.h)
    assert_contract(ep, "/dataset-versions/{version_id}/episodes/{episode_index}")
    eb = ep.json()
    assert eb["index"] == 3 and len(eb["timestamps"]) == 100 and len(eb["series"]) == 12
    assert all(len(s["values"]) == 100 for s in eb["series"])
    video = eb["videos"][0]
    assert video["codec"] == "av1" and video["browser_playable_hint"] is False
    assert video["preview_media_path"] == f"previews/{CAM}/episode_000003.mp4"
    assert (await client.get(f"/dataset-versions/{vid}/episodes/20", headers=a.h)).status_code == 404

    # H.264 preview clip, whole and ranged; thumbnail; original AV1 with Range; meta json.
    clip = await client.get(f"/dataset-versions/{vid}/media/{video['preview_media_path']}", headers=a.h)
    assert clip.status_code == 200 and clip.headers["content-type"] == "video/mp4"
    assert clip.headers["accept-ranges"] == "bytes" and "immutable" in clip.headers["cache-control"]
    assert clip.content[4:8] == b"ftyp"
    part = await client.get(
        f"/dataset-versions/{vid}/media/{video['preview_media_path']}", headers={**a.h, "Range": "bytes=0-99"}
    )
    assert part.status_code == 206 and part.content == clip.content[:100]
    assert part.headers["content-range"] == f"bytes 0-99/{len(clip.content)}"
    thumb = await client.get(f"/dataset-versions/{vid}/media/{video['thumbnail_media_path']}", headers=a.h)
    assert thumb.headers["content-type"] == "image/jpeg" and thumb.content[:3] == b"\xff\xd8\xff"
    orig = await client.get(
        f"/dataset-versions/{vid}/media/{video['media_path']}", headers={**a.h, "Range": "bytes=147414000-"}
    )
    assert orig.status_code == 206 and len(orig.content) == 147414409 - 147414000
    bad = await client.get(
        f"/dataset-versions/{vid}/media/{video['media_path']}", headers={**a.h, "Range": "bytes=999999999-"}
    )
    assert bad.status_code == 416 and bad.headers["content-range"] == "bytes */147414409"
    assert_contract(bad, "/dataset-versions/{version_id}/media/{path}")
    info = await client.get(f"/dataset-versions/{vid}/media/meta%2Finfo.json", headers=a.h)
    assert info.status_code == 200 and info.json()["total_episodes"] == 20
    for forbidden in ("data/chunk-000/file-000.parquet", "..%2F..%2Fx", "meta%2F..%2Fmeta%2Finfo.json"):
        assert (
            await client.get(f"/dataset-versions/{vid}/media/{forbidden}", headers=a.h)
        ).status_code == 404

    # Tar download: every file byte-identical to the archive content.
    tr = await client.get(f"/dataset-versions/{vid}/archive", headers=a.h)
    assert tr.status_code == 200 and tr.headers["content-type"] == "application/x-tar"
    assert 'filename="picknplace-20261114-v1.tar"' in tr.headers["content-disposition"]
    with tarfile.open(fileobj=io.BytesIO(tr.content)) as tf:
        names = sorted(m.name for m in tf.getmembers())
        mp4 = tf.extractfile(f"picknplace-20261114-v1/videos/{CAM}/chunk-000/file-000.mp4")
        assert mp4 is not None
        golden_mp4 = (
            Path("~/datasets/robotics/so101_picknplace_20261114/videos")
            / CAM
            / "chunk-000/file-000.mp4"
        )
        if golden_mp4.is_file():
            assert (
                hashlib.sha256(mp4.read()).hexdigest() == hashlib.sha256(golden_mp4.read_bytes()).hexdigest()
            )
    assert len(names) == 6 and names[0] == "picknplace-20261114-v1/data/chunk-000/file-000.parquet"
