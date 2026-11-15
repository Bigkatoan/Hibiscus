"""Claim SQL (fair-share, quotas, placement), dataset cache, argv finalisation, classification."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from core.events import Outbox
from core.testing import Services, contract_metadata, insert_run, seed_basic
from train import argv as argvmod
from train.checkpoints import is_complete
from train.classify import ExitFacts, classify, is_infra
from train.dataset_cache import DatasetCache, DatasetUnavailableError, content_hash
from train.queue import claim_run
from train.tests.harness import store_for
from train.worker import unsupported_policies


def _claim(engine: Engine, gpu: str = "cuda0", vram: int = 12288, worker: str = "w") -> uuid.UUID | None:
    with engine.begin() as conn:
        return claim_run(
            conn,
            gpu_id=gpu,
            gpu_total_vram_mb=vram,
            unsupported=unsupported_policies(vram),
            worker_id=worker,
            lease_ttl_s=60,
            outbox=Outbox(),
        )


def _gpu(engine: Engine, gid: str, vram: int) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO gpu_nodes (id, host, device_index, name, total_vram_mb, compute_capability, "
                "supports_bf16, supports_fast_fp16, status) VALUES (:i, 'h', :d, 'g', :v, '8.6', true, true, 'online')"  # noqa: E501
            ),
            {"i": gid, "d": int(gid[-1]), "v": vram},
        )


def _user(engine: Engine, seed: object) -> uuid.UUID:
    m = contract_metadata()
    from sqlalchemy.orm import Session

    uid = uuid.uuid4()
    with Session(engine) as s:
        s.add(m.User(id=uid, email=f"{uid.hex[:8]}@x.io", display_name="B", password_hash="x"))  # noqa: S106
        s.flush()
        s.add(m.Membership(workspace_id=seed.workspace_id, user_id=uid, role=m.WorkspaceRole.MEMBER))  # type: ignore[attr-defined]
        s.commit()
    return uid


def test_priority_then_fair_share_then_fifo(engine: Engine) -> None:
    _gpu(engine, "cuda0", 12288)
    seed = seed_basic(engine)
    heavy, light = seed.user_id, _user(engine, seed)
    with engine.begin() as conn:  # make a 2-workspace quota so both users may run concurrently
        conn.execute(
            text("INSERT INTO quotas (id, workspace_id, max_concurrent_runs) VALUES (:i, :w, 5)"),
            {"i": uuid.uuid4(), "w": seed.workspace_id},
        )
    # heavy user burned GPU time recently
    insert_run(engine, seed, created_by=heavy, status="succeeded", gpu_seconds=36000.0)
    a = insert_run(engine, seed, created_by=heavy)  # older
    b = insert_run(engine, seed, created_by=light)  # newer, but lighter user
    c = insert_run(engine, seed, created_by=heavy, priority=5)
    assert _claim(engine) == c  # priority wins
    assert _claim(engine) == b  # then fair-share
    assert _claim(engine) == a


def test_concurrency_quota_default_one(engine: Engine) -> None:
    _gpu(engine, "cuda0", 12288)
    _gpu(engine, "cuda1", 24576)
    seed = seed_basic(engine)
    r1 = insert_run(engine, seed)
    insert_run(engine, seed)
    assert _claim(engine, "cuda0") == r1
    assert _claim(engine, "cuda1", 24576) is None  # default max_concurrent_runs = 1
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO quotas (id, workspace_id, user_id, max_concurrent_runs) VALUES (:i,:w,:u,2)"),
            {"i": uuid.uuid4(), "w": seed.workspace_id, "u": seed.user_id},
        )
    assert _claim(engine, "cuda1", 24576) is not None


def test_placement_vram_requested_gpu_and_policy(engine: Engine) -> None:
    _gpu(engine, "cuda0", 12288)
    _gpu(engine, "cuda1", 24576)
    seed = seed_basic(engine)
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO quotas (id, workspace_id, max_concurrent_runs) VALUES (:i,:w,10)"),
            {"i": uuid.uuid4(), "w": seed.workspace_id},
        )
    big = insert_run(engine, seed, required_vram_mb=16000)
    pi = insert_run(engine, seed, policy_type="pi0")
    pinned = insert_run(engine, seed, requested_gpu_id="cuda1")
    assert _claim(engine, "cuda0") is None  # none fits the 3060
    got = {_claim(engine, "cuda1", 24576) for _ in range(3)}
    assert got == {big, pi, pinned}
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT status, gpu_node_id, attempt, lease_owner FROM runs WHERE id=:i"), {"i": big}
        ).one()
        cur = conn.execute(text("SELECT current_run_id FROM gpu_nodes WHERE id='cuda1'")).scalar_one()
    assert tuple(row) == ("preparing", "cuda1", 1, "w") and cur in got


def test_skip_locked_two_workers(engine: Engine) -> None:
    _gpu(engine, "cuda0", 12288)
    _gpu(engine, "cuda1", 24576)
    seed = seed_basic(engine)
    u2 = _user(engine, seed)
    insert_run(engine, seed)
    insert_run(engine, seed, created_by=u2)
    with engine.begin() as c1, engine.begin() as c2:
        a = claim_run(
            c1,
            gpu_id="cuda0",
            gpu_total_vram_mb=12288,
            unsupported=[],
            worker_id="a",
            lease_ttl_s=60,
            outbox=Outbox(),
        )
        b = claim_run(
            c2,
            gpu_id="cuda1",
            gpu_total_vram_mb=24576,
            unsupported=[],
            worker_id="b",
            lease_ttl_s=60,
            outbox=Outbox(),
        )
    assert a and b and a != b


def test_dataset_cache_download_verify_and_lru(services: Services, tmp_path: Path) -> None:
    st = store_for(services)
    src = tmp_path / "ds"
    (src / "meta").mkdir(parents=True)
    (src / "meta" / "info.json").write_text("{}")
    (src / "data.bin").write_bytes(b"1" * 5000)
    st.upload_dir(src, "hibiscus-datasets", "c/v1")
    cache = DatasetCache(tmp_path / "cache", st, max_bytes=6000)
    h = content_hash(src)
    p = cache.ensure("v1", "s3://hibiscus-datasets/c/v1/", h)
    assert (p / "data.bin").read_bytes() == b"1" * 5000 and (p / ".complete").read_text() == h
    assert cache.ensure("v1", "s3://hibiscus-datasets/c/v1/", h) == p  # cached
    with pytest.raises(DatasetUnavailableError, match="hash mismatch"):
        cache.ensure("v2", "s3://hibiscus-datasets/c/v1/", "0" * 64)
    with pytest.raises(DatasetUnavailableError, match="no LeRobot dataset"):
        cache.ensure("v3", "s3://hibiscus-datasets/nothing/", None)
    st.upload_dir(src, "hibiscus-datasets", "c/v4")
    cache.ensure("v4", "s3://hibiscus-datasets/c/v4/", h)  # evicts v1 (LRU) to stay under 6000 bytes
    assert not (tmp_path / "cache" / "datasets" / "v1").exists()


def test_content_hash_matches_contract_definition(tmp_path: Path) -> None:
    import hashlib

    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "x").write_bytes(b"x")
    (tmp_path / "y").write_bytes(b"yy")
    lines = sorted(
        [f"a/x\0{hashlib.sha256(b'x').hexdigest()}\n", f"y\0{hashlib.sha256(b'yy').hexdigest()}\n"]
    )
    assert content_hash(tmp_path) == hashlib.sha256("".join(lines).encode()).hexdigest()


def test_argv_finalize_and_resume(tmp_path: Path) -> None:
    args = [
        "lerobot-train",
        "--policy.type=act",
        "--policy.pretrained_path={{INIT_PATH}}",
        "--dataset.root={{DATASET_ROOT}}",
        "--output_dir={{OUTPUT_DIR}}",
        "--num_workers=8",
        '--accelerator.mixed_precision="bf16"',
    ]
    out = argvmod.finalize_fresh(
        args,
        bin_path="/bin/lt",
        dataset_root=Path("/c/d"),
        output_dir=Path("/s/o"),
        init_path=None,
        mixed_precision="no",
    )
    assert out == [
        "/bin/lt",
        "--policy.type=act",
        "--dataset.root=/c/d",
        "--output_dir=/s/o",
        "--num_workers=4",
        '--accelerator.mixed_precision="no"',
    ]
    out2 = argvmod.finalize_fresh(
        args[:3],
        bin_path="x",
        dataset_root=Path("/d"),
        output_dir=Path("/o"),
        init_path=Path("/i/pm"),
        mixed_precision="bf16",
    )
    assert "--policy.pretrained_path=/i/pm" in out2 and out2[-1] == '--accelerator.mixed_precision="bf16"'
    res = argvmod.finalize_resume(
        bin_path="x", output_dir=Path("/o"), step=40, total_steps=100, mixed_precision="no"
    )
    assert res == [
        "x",
        "--config_path=/o/checkpoints/000040/pretrained_model/train_config.json",
        "--resume=true",
        "--steps=100",
        '--accelerator.mixed_precision="no"',
    ]
    assert argvmod.override(["x", "--steps=5", "--log_freq=1"], steps="20", save_checkpoint="false") == [
        "x",
        "--log_freq=1",
        "--steps=20",
        "--save_checkpoint=false",
    ]


@pytest.mark.parametrize(
    ("facts", "code"),
    [
        (
            ExitFacts(
                1,
                False,
                False,
                False,
                'File "/x/draccus/parsers/decoding.py", line 1\ndraccus.utils.ParsingError: bad',
            ),
            "config_invalid",
        ),
        (
            ExitFacts(
                1, False, False, False, 'File "/x/lerobot/configs/train.py", line 9\nValueError: no policy'
            ),
            "config_invalid",
        ),
        (
            ExitFacts(1, False, False, False, 'File "/x/lerobot/datasets/x.py"\nValueError: bad video'),
            "process_crashed",
        ),
        (ExitFacts(1, True, False, False, "KeyError: 'observation.images.top'"), "dataset_feature_mismatch"),
        (ExitFacts(1, True, True, False, "torch.OutOfMemoryError: CUDA out of memory"), "oom"),
        (ExitFacts(1, True, False, True, "RuntimeError: CUDA error: an illegal memory access"), "gpu_error"),
        (ExitFacts(-9, True, False, False, ""), "process_crashed"),
    ],
)
def test_classify(facts: ExitFacts, code: str) -> None:
    got, msg = classify(facts)
    assert got == code and msg
    assert is_infra(got) == (code in {"process_crashed", "gpu_error"})


def test_unsupported_policies_by_vram() -> None:
    assert unsupported_policies(12288) == ["pi0", "pi05"]
    assert unsupported_policies(24576) == []


def test_torch_arch_support(monkeypatch: pytest.MonkeyPatch) -> None:
    import torch

    from train.telemetry import torch_supports

    monkeypatch.setattr(torch.cuda, "get_arch_list", lambda: ["sm_75", "sm_80", "sm_86", "sm_90", "sm_120"])
    assert torch_supports("8.6") is True and torch_supports("8.9") is True
    assert torch_supports("6.1") is False  # Tesla P40 with torch 2.15+cu132 (CR-A4-7)
    monkeypatch.setattr(torch.cuda, "get_arch_list", lambda: ["sm_50", "compute_50"])
    assert torch_supports("6.1") is True  # PTX JIT
    monkeypatch.setattr(torch.cuda, "get_arch_list", list)
    assert torch_supports("6.1") is None


def test_checkpoint_complete_once_last_points_at_it_or_newer(tmp_path: Path) -> None:
    """A checkpoint superseded by the next save before its upload started is still complete."""
    ck = tmp_path / "checkpoints"
    for step in (20, 40):
        d = ck / f"{step:06d}"
        (d / "pretrained_model").mkdir(parents=True)
        (d / "training_state").mkdir(parents=True)
        (d / "pretrained_model" / "config.json").write_text("{}")
    (ck / "000020" / "training_state" / "training_step.json").write_text("{}")
    assert not is_complete(tmp_path, 20)  # no ``last`` yet: still being written
    (ck / "last").symlink_to("000020")
    assert is_complete(tmp_path, 20) and not is_complete(tmp_path, 40)  # 40: no training_step.json
    (ck / "000040" / "training_state" / "training_step.json").write_text("{}")
    assert not is_complete(tmp_path, 40)  # files there, ``last`` not repointed yet
    (ck / "last").unlink()
    (ck / "last").symlink_to("000040")
    assert is_complete(tmp_path, 20) and is_complete(tmp_path, 40)
    assert not is_complete(tmp_path, 60)
