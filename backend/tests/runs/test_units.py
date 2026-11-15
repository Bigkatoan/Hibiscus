"""Pure unit tests: config resolution, cross-field rules, split, argv serialisation, LTTB, zip index."""

from __future__ import annotations

import io
import zipfile

import pytest

from app.core.pagination import decode_cursor, encode_cursor
from app.models.zipindex import read_index, stream_member
from app.runs.argv import build_argv, fmt_value
from app.runs.catalog import get_catalog, gpu_support_level, unsupported_policies_for_vram
from app.runs.config import cross_field_errors, eval_rule, heldout_split, resolve_config
from app.runs.errors import ProblemError
from app.runs.metrics import downsample_series, lttb
from app.runs.preflight import camera_keys, estimate_cache_key, heuristic_estimate, image_shapes


def test_resolve_defaults_preset_user_order() -> None:
    cat = get_catalog()
    r = resolve_config(
        cat,
        "act",
        {"policy": {"chunk_size": 50, "n_action_steps": 50}, "train": {"steps": 77}},
        preset="quick",
        seed=7,
    )
    assert r.train["steps"] == 77 and r.train["save_freq"] == 5000 and r.train["log_freq"] == 100
    assert r.train["seed"] == 7 and r.policy["chunk_size"] == 50 and r.policy["dim_model"] == 512
    s = resolve_config(cat, "smolvla", {}, preset="quick")
    assert s.train["batch_size"] == 4  # per_policy override
    pi = resolve_config(cat, "pi0", {}, preset="finetune")
    assert (
        pi.train["peft"] == {"method_type": "LORA", "r": 16} and pi.policy["gradient_checkpointing"] is True
    )


def test_resolve_rejects_unknown_and_bad_types() -> None:
    cat = get_catalog()
    with pytest.raises(ProblemError) as e:
        resolve_config(cat, "act", {"policy": {"nope": 1}, "train": {"steps": 0}}, preset=None)
    assert e.value.code == "validation_failed"
    locs = [err["loc"] for err in e.value.ext["errors"]]
    assert ["body", "config", "policy"] in locs and ["body", "config", "train", "steps"] in locs
    with pytest.raises(ProblemError) as e:
        resolve_config(
            cat, "diffusion", {"policy": {"horizon": 8, "n_obs_steps": 2, "n_action_steps": 8}}, preset=None
        )
    assert e.value.code == "policy_config_invalid"


def test_cross_field_rules_and_evaluator_is_safe() -> None:
    assert eval_rule("n_action_steps <= chunk_size", {"n_action_steps": 1, "chunk_size": 2})
    assert eval_rule(
        "temporal_ensemble_coeff == null or n_action_steps == 1",
        {"temporal_ensemble_coeff": None, "n_action_steps": 5},
    )
    assert not eval_rule(
        "temporal_ensemble_coeff == null or n_action_steps == 1",
        {"temporal_ensemble_coeff": 0.01, "n_action_steps": 5},
    )
    assert eval_rule(
        "n_action_steps <= horizon - n_obs_steps + 1", {"n_action_steps": 8, "horizon": 16, "n_obs_steps": 2}
    )
    with pytest.raises(ValueError, match="unsupported"):
        eval_rule("__import__('os')", {})
    schema = {"x-hibiscus": {"cross_field_rules": [{"rule": "a <= b", "code": "policy_config_invalid"}]}}
    assert cross_field_errors(schema, {"a": 3, "b": 2})[0]["loc"][-1] == "a"


def test_heldout_split_spec() -> None:
    held, train = heldout_split(20, 0.1, 1000)
    assert len(held) == 2 and sorted(held + train) == list(range(20))
    assert heldout_split(20, 0.1, 1000) == (held, train)  # reproducible
    assert heldout_split(20, 0.0, 1) == ([], list(range(20)))
    assert heldout_split(3, 0.01, 1)[0] and len(heldout_split(2, 0.49, 1)[0]) == 1  # k>=1, k<=n-1
    assert heldout_split(5, 0.1, 1, [4, 0]) == ([0, 4], [1, 2, 3])
    with pytest.raises(ProblemError):
        heldout_split(5, 0.1, 1, [9])


@pytest.mark.parametrize(
    ("v", "out"),
    [
        (True, "true"),
        (None, "null"),
        (3, "3"),
        (1e-05, "1.0e-05"),
        (0.5, "0.5"),
        ("no", '"no"'),
        ("resnet18", "resnet18"),
        ("1.5", '"1.5"'),
        ("", '""'),
        ([1, 2], "[1,2]"),
        ({"a": 1}, '{"a":1}'),
        ("on", '"on"'),
        ("mean_std", "mean_std"),
    ],
)
def test_fmt_value_for_draccus(v: object, out: str) -> None:
    assert fmt_value(v) == out


def test_build_argv_only_non_defaults_and_all_train_keys() -> None:
    cat = get_catalog()
    r = resolve_config(cat, "act", {"policy": {"chunk_size": 50, "n_action_steps": 50}}, preset="quick")
    argv = build_argv(
        cat,
        "act",
        r.policy,
        r.train,
        run_id="RID",
        dataset_repo_id="local/ds",
        train_episodes=[3, 1, 2],
        has_init_from=True,
    )
    assert argv[:4] == [
        "lerobot-train",
        "--policy.type=act",
        "--policy.device=cuda",
        "--policy.push_to_hub=false",
    ]
    assert "--policy.chunk_size=50" in argv and not any(a.startswith("--policy.dim_model") for a in argv)
    assert "--dataset.episodes=[1,2,3]" in argv and "--policy.pretrained_path={{INIT_PATH}}" in argv
    for flag in (
        "--steps=",
        "--batch_size=",
        "--seed=",
        "--num_workers=",
        "--log_freq=",
        "--save_freq=",
        "--accelerator.mixed_precision=",
        "--dataset.image_transforms.enable=",
        "--tf32=",
    ):
        assert any(a.startswith(flag) for a in argv), flag
    assert argv[-2:] == ["--save_checkpoint=true", "--trackio.enable=false"]
    assert not any(a.startswith("--wandb") for a in argv)
    pi = resolve_config(cat, "pi0", {}, preset="finetune")
    pa = build_argv(
        cat,
        "pi0",
        pi.policy,
        pi.train,
        run_id="R",
        dataset_repo_id="local/ds",
        train_episodes=[0],
        has_init_from=True,
    )
    assert "--peft.method_type=LORA" in pa and "--peft.r=16" in pa


def test_gpu_support_matrix() -> None:
    assert gpu_support_level("pi0", 12288) == "unsupported" and gpu_support_level("pi0", 24576) == "limited"
    assert (
        gpu_support_level("smolvla", 12288) == "limited"
        and gpu_support_level("smolvla", 24576) == "supported"
    )
    assert gpu_support_level("act", 12288) == "supported"
    assert unsupported_policies_for_vram(12288) == ["pi0", "pi05"]


def test_estimate_helpers() -> None:
    feats = {
        "observation.images.b": {"dtype": "video", "shape": [360, 640, 3]},
        "observation.images.a": {"dtype": "image", "shape": [96, 96, 3]},
        "action": {"dtype": "float32"},
    }
    assert camera_keys(feats) == ["observation.images.a", "observation.images.b"]
    assert image_shapes(feats) == [[3, 96, 96], [3, 360, 640]]
    k1 = estimate_cache_key("act", "g", 8, "no", [[3, 1, 1]], "h", "0.7.1")
    assert k1 != estimate_cache_key("act", "g", 16, "no", [[3, 1, 1]], "h", "0.7.1") and len(k1) == 64
    vram, sps = heuristic_estimate("act", 8, [[3, 360, 640]])
    assert vram == 2450 and abs(sps - 0.11) < 1e-9


def test_lttb_and_nonfinite() -> None:
    pts = [(i, float((i * 37) % 101)) for i in range(1000)]
    d = lttb(pts, 100)
    assert len(d) == 100 and d[0] == pts[0] and d[-1] == pts[-1]
    s = downsample_series("loss", [*pts[:10], (10, float("inf"))], 50)
    assert s["has_nonfinite"] and s["values"][-1] is None and not s["downsampled"]


def test_cursor_roundtrip_and_tamper() -> None:
    c = encode_cursor({"t": "x", "i": "y"})
    assert decode_cursor(c) == {"t": "x", "i": "y"}
    with pytest.raises(ProblemError):
        decode_cursor(c[:-2] + ("A" if c[-2] != "A" else "B") + c[-1])


async def test_zip_index_stored_deflated_and_zip64() -> None:
    buf = io.BytesIO()
    big = bytes(range(256)) * 4096
    with zipfile.ZipFile(buf, "w", allowZip64=True) as z:
        z.writestr("b/x.safetensors", big, compress_type=zipfile.ZIP_STORED)
        z.writestr("b/y.json", b'{"k": "v"}' * 1000, compress_type=zipfile.ZIP_DEFLATED)
        with z.open("b/z.bin", "w", force_zip64=True) as f:
            f.write(b"z" * 5000)
    blob = buf.getvalue()

    async def fetch(lo: int, hi: int) -> bytes:
        return blob[lo : hi + 1]

    idx = await read_index(fetch, len(blob))
    assert set(idx) == {"b/x.safetensors", "b/y.json", "b/z.bin"}

    async def read(name: str, a: int, b: int) -> bytes:
        return b"".join([c async for c in stream_member(fetch, idx[name], a, b, chunk=1000)])

    assert await read("b/x.safetensors", 0, len(big) - 1) == big
    assert await read("b/x.safetensors", 300, 1299) == big[300:1300]
    y = b'{"k": "v"}' * 1000
    assert await read("b/y.json", 0, len(y) - 1) == y and await read("b/y.json", 5, 25) == y[5:26]
    assert await read("b/z.bin", 0, 4999) == b"z" * 5000
