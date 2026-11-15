from __future__ import annotations

import hashlib
import io
import os
import tarfile
from pathlib import Path

import httpx
import pytest

from hibiscus.api import ApiError, Backoff, HibiscusApi
from hibiscus.archive import FileSource, SourceChangedError, VirtualTar
from hibiscus.upload import MIB, Uploader, UploadEvents, UploadState
from tests.conftest import GOLDEN_DATASET, GOLDEN_RAR
from tests.fake_server import BASE, TOKEN, FakeHibiscus, Fault

PART = 5 * MIB  # smallest legal part size, keeps tests fast


def _archive(tmp: Path, size: int, name: str = "rec.tar") -> Path:
    p = tmp / name
    p.write_bytes(os.urandom(size))
    return p


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_push_archive_multi_part(fake: FakeHibiscus, api: HibiscusApi, tmp_path: Path) -> None:
    src_path = _archive(tmp_path, 2 * PART + 12345)
    res = Uploader(api, parallel=2).push(FileSource(src_path), new_dataset_name="rec", part_size=PART)
    assert res.sent_parts == 3 and res.resumed_parts == 0
    s = fake.uploads[res.upload_id]
    assert s["status"] == "completed"
    assert s["assembled_sha256"] == _sha(src_path) == res.sha256
    assert fake.assembled(res.upload_id).read_bytes() == src_path.read_bytes()
    assert sorted(r.body_size for r in fake.puts()) == [12345, PART, PART]
    v = fake.versions[res.version_id]
    assert v["status"] == "pending" and fake.datasets[res.dataset_id]["name"] == "rec"
    # resume state cleaned up after complete
    assert not list((Path(os.environ["HIBISCUS_STATE_DIR"]) / "uploads").glob("*.json"))


def test_push_new_version_of_existing_dataset(fake: FakeHibiscus, api: HibiscusApi, tmp_path: Path) -> None:
    ds = fake.add_dataset("so101_picknplace")
    res = Uploader(api).push(FileSource(_archive(tmp_path, 1000)), dataset_id=ds["id"], part_size=PART)
    assert res.dataset_id == ds["id"] and res.version == 2


def test_resume_after_interruption(fake: FakeHibiscus, api: HibiscusApi, tmp_path: Path) -> None:
    """Process 'dies' after part 2: a fresh Uploader resumes from the state file and server part list."""
    src_path = _archive(tmp_path, 4 * PART + 7)
    fake.faults.append(Fault("uploadPart", "connect", part_number=3, times=99))
    first = Uploader(api, parallel=1, max_attempts=2)
    with pytest.raises(httpx.ConnectError):
        first.push(FileSource(src_path), new_dataset_name="rec", part_size=PART)
    (upload_id,) = fake.uploads
    assert sorted(fake.uploads[upload_id]["parts"]) == [1, 2]
    state_files = list((Path(os.environ["HIBISCUS_STATE_DIR"]) / "uploads").glob("*.json"))
    assert len(state_files) == 1
    fake.faults.clear()

    # "new process": new client, new uploader, nothing in memory
    with HibiscusApi(
        BASE, TOKEN, workspace_id=fake.workspace_id, backoff=Backoff(sleep=lambda s: None)
    ) as api2:
        events: list[str] = []
        res = Uploader(api2, parallel=2, events=UploadEvents(on_info=events.append)).push(
            FileSource(src_path), new_dataset_name="rec", part_size=PART
        )
    assert res.upload_id == upload_id
    assert res.resumed_parts == 2 and res.sent_parts == 3
    assert "resuming previous upload" in events
    sent = [int(r.path.rsplit("/", 1)[1]) for r in fake.puts()]
    assert sent.count(1) == 1 and sent.count(2) == 1  # never re-sent
    assert fake.uploads[upload_id]["assembled_sha256"] == _sha(src_path)
    # only one initUpload: the resume used GET /uploads/{id}
    assert [r.operation_id for r in fake.requests].count("initUpload") == 1
    assert "getUpload" in [r.operation_id for r in fake.requests]


def test_resume_without_state_file_uses_server_session(
    fake: FakeHibiscus, api: HibiscusApi, tmp_path: Path
) -> None:
    src_path = _archive(tmp_path, 3 * PART)
    fake.faults.append(Fault("uploadPart", "connect", part_number=2, times=99))
    with pytest.raises(httpx.ConnectError):
        Uploader(api, parallel=1, max_attempts=1).push(
            FileSource(src_path), new_dataset_name="r", part_size=PART
        )
    for f in (Path(os.environ["HIBISCUS_STATE_DIR"]) / "uploads").glob("*.json"):
        f.unlink()  # e.g. a different machine / wiped state dir
    fake.faults.clear()
    res = Uploader(api).push(FileSource(src_path), new_dataset_name="r", part_size=PART)
    assert res.resumed_parts == 1 and res.sent_parts == 2
    assert len(fake.uploads) == 1  # server returned the existing active session (200)


def test_retries_transient_errors_with_backoff(
    fake: FakeHibiscus, api: HibiscusApi, tmp_path: Path, sleeps: list[float]
) -> None:
    src_path = _archive(tmp_path, 2 * PART + 1)
    fake.faults += [
        Fault("uploadPart", "status:502", part_number=1, times=2),
        Fault("uploadPart", "status:429", part_number=2, times=1, retry_after=7),
        Fault("uploadPart", "read_timeout", part_number=3, times=1),
        Fault("initUpload", "connect", times=1),
    ]
    retries: list[tuple[int, int]] = []
    ev = UploadEvents(on_retry=lambda part, attempt, exc, delay: retries.append((part, attempt)))
    res = Uploader(api, parallel=1, events=ev).push(
        FileSource(src_path), new_dataset_name="r", part_size=PART
    )
    assert fake.uploads[res.upload_id]["assembled_sha256"] == _sha(src_path)
    assert retries == [(1, 1), (1, 2), (2, 1), (3, 1)]
    # exponential 1, 2 for part 1; Retry-After 7 honoured for part 2; 1 for part 3; 1 for initUpload
    assert sleeps == [1.0, 1.0, 2.0, 7.0, 1.0]


def test_lost_response_is_idempotent(fake: FakeHibiscus, api: HibiscusApi, tmp_path: Path) -> None:
    """Server stored the part but the response was lost: re-sending the same part is harmless."""
    src_path = _archive(tmp_path, PART + 10)
    fake.faults.append(Fault("uploadPart", "lost_response", part_number=1))
    res = Uploader(api, parallel=1).push(FileSource(src_path), new_dataset_name="r", part_size=PART)
    assert fake.uploads[res.upload_id]["assembled_sha256"] == _sha(src_path)
    assert [int(r.path.rsplit("/", 1)[1]) for r in fake.puts()].count(1) == 2


def test_checksum_mismatch_resent_once(fake: FakeHibiscus, api: HibiscusApi, tmp_path: Path) -> None:
    src_path = _archive(tmp_path, PART + 10)
    fake.faults.append(Fault("uploadPart", "corrupt", part_number=2))
    res = Uploader(api, parallel=1).push(FileSource(src_path), new_dataset_name="r", part_size=PART)
    assert fake.uploads[res.upload_id]["assembled_sha256"] == _sha(src_path)


def test_non_retryable_error_surfaces(fake: FakeHibiscus, api: HibiscusApi, tmp_path: Path) -> None:
    src_path = _archive(tmp_path, PART + 10)
    fake.faults.append(Fault("uploadPart", "corrupt", part_number=1, times=5))
    with pytest.raises(ApiError) as ei:
        Uploader(api, parallel=1).push(FileSource(src_path), new_dataset_name="r", part_size=PART)
    assert ei.value.code == "upload_part_checksum_mismatch" and ei.value.status == 422


def test_server_clamped_part_size_rehashes(tmp_path: Path, sleeps: list[float]) -> None:
    import respx

    server = FakeHibiscus(tmp_path / "srv", server_part_size=5 * MIB)
    src_path = _archive(tmp_path, 12 * MIB)
    with respx.mock(assert_all_called=False) as router:
        server.mount(router)
        with HibiscusApi(
            BASE, TOKEN, workspace_id=server.workspace_id, backoff=Backoff(sleep=sleeps.append)
        ) as a:
            res = Uploader(a).push(FileSource(src_path), new_dataset_name="r", part_size=64 * MIB)
    assert server.uploads[res.upload_id]["part_size"] == 5 * MIB
    assert sorted(r.body_size for r in server.puts()) == [2 * MIB, 5 * MIB, 5 * MIB]
    assert server.uploads[res.upload_id]["assembled_sha256"] == _sha(src_path)


def test_expired_session_starts_over(fake: FakeHibiscus, api: HibiscusApi, tmp_path: Path) -> None:
    src_path = _archive(tmp_path, 2 * PART)
    fake.faults.append(Fault("uploadPart", "connect", part_number=2, times=99))
    with pytest.raises(httpx.ConnectError):
        Uploader(api, parallel=1, max_attempts=1).push(
            FileSource(src_path), new_dataset_name="r", part_size=PART
        )
    (old_id,) = fake.uploads
    fake.uploads[old_id]["status"] = "expired"
    fake.faults.clear()
    res = Uploader(api).push(FileSource(src_path), new_dataset_name="r", part_size=PART)
    assert res.upload_id != old_id and res.sent_parts == 2


def test_source_changed_between_runs_restarts(fake: FakeHibiscus, api: HibiscusApi, tmp_path: Path) -> None:
    src_path = _archive(tmp_path, 2 * PART)
    fake.faults.append(Fault("uploadPart", "connect", part_number=2, times=99))
    with pytest.raises(httpx.ConnectError):
        Uploader(api, parallel=1, max_attempts=1).push(
            FileSource(src_path), new_dataset_name="r", part_size=PART
        )
    fake.faults.clear()
    src_path.write_bytes(os.urandom(2 * PART))
    infos: list[str] = []
    res = Uploader(api, events=UploadEvents(on_info=infos.append)).push(
        FileSource(src_path), new_dataset_name="r", part_size=PART
    )
    assert any("starting over" in i for i in infos)
    assert fake.uploads[res.upload_id]["assembled_sha256"] == _sha(src_path)


def test_source_modified_during_upload_aborts(fake: FakeHibiscus, api: HibiscusApi, tmp_path: Path) -> None:
    src_path = _archive(tmp_path, 2 * PART)
    src = FileSource(src_path)
    uploader = Uploader(api, parallel=1)

    def tamper(part: int, n: int) -> None:
        if part == 1:
            with src_path.open("r+b") as fh:
                fh.seek(PART + 5)
                fh.write(b"\xff\xff")

    uploader.events.on_part_done = tamper
    with pytest.raises(SourceChangedError):
        uploader.push(src, new_dataset_name="r", part_size=PART)


def test_state_file_is_private(fake: FakeHibiscus, api: HibiscusApi, tmp_path: Path) -> None:
    src_path = _archive(tmp_path, 2 * PART)
    fake.faults.append(Fault("uploadPart", "connect", part_number=2, times=99))
    with pytest.raises(httpx.ConnectError):
        Uploader(api, parallel=1, max_attempts=1).push(
            FileSource(src_path), new_dataset_name="r", part_size=PART
        )
    (f,) = (Path(os.environ["HIBISCUS_STATE_DIR"]) / "uploads").glob("*.json")
    assert f.stat().st_mode & 0o777 == 0o600
    key = f.stem
    st = UploadState.load(key)
    assert st is not None and st.upload_id in fake.uploads and len(st.part_sha256) == 2


# ---------------------------------------------------------------------------------------- golden data
@pytest.mark.skipif(not GOLDEN_RAR.is_file(), reason="golden .rar not present on this machine")
def test_golden_rar_chunked_upload_sizes(fake: FakeHibiscus, api: HibiscusApi) -> None:
    """The real 144.8 MB RAR5 archive goes up in ≤ 64 MiB parts (Cloudflare 100 MB) and re-assembles."""
    size = GOLDEN_RAR.stat().st_size
    src = FileSource(GOLDEN_RAR)
    assert src.archive_format == "rar"
    res = Uploader(api, parallel=2).push(src, new_dataset_name="Picknplace_20261114", part_size=64 * MIB)
    puts = sorted(fake.puts(), key=lambda r: int(r.path.rsplit("/", 1)[1]))
    sizes = [r.body_size for r in puts]
    assert sizes == [64 * MIB, 64 * MIB, size - 128 * MIB]
    assert max(sizes) < 100_000_000
    assert all(int(r.headers["content-length"]) == r.body_size for r in puts)
    s = fake.uploads[res.upload_id]
    assert s["archive_format"] == "rar" and s["filename"] == GOLDEN_RAR.name and s["part_count"] == 3
    expected = hashlib.sha256()
    with GOLDEN_RAR.open("rb") as fh:
        while chunk := fh.read(8 * MIB):
            expected.update(chunk)
    assert s["assembled_sha256"] == res.sha256 == expected.hexdigest()
    assert fake.assembled(res.upload_id).stat().st_size == size


@pytest.mark.skipif(not GOLDEN_DATASET.is_dir(), reason="golden dataset not present on this machine")
def test_golden_dataset_dir_tarred_and_uploaded(fake: FakeHibiscus, api: HibiscusApi) -> None:
    vt = VirtualTar(GOLDEN_DATASET)
    res = Uploader(api, parallel=2).push(vt, new_dataset_name="so101_picknplace", part_size=64 * MIB)
    sizes = sorted((r.body_size for r in fake.puts()), reverse=True)
    assert sizes[:2] == [64 * MIB, 64 * MIB] and sum(sizes) == vt.size and len(sizes) == 3
    s = fake.uploads[res.upload_id]
    assert s["archive_format"] == "tar" and s["assembled_sha256"] == s["sha256"]
    blob = fake.assembled(res.upload_id).read_bytes()
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:") as tf:
        members = {m.name: m for m in tf.getmembers() if m.isfile()}
        for rel in (
            "meta/info.json",
            "meta/stats.json",
            "data/chunk-000/file-000.parquet",
            "videos/observation.images.wrist_cam/chunk-000/file-000.mp4",
        ):
            m = members[f"{GOLDEN_DATASET.name}/{rel}"]
            fh = tf.extractfile(m)
            assert fh is not None
            assert hashlib.sha256(fh.read()).hexdigest() == _sha(GOLDEN_DATASET / rel)
    assert len(members) == vt.file_count
