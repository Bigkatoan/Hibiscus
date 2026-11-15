from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from eval.offline import DISCLAIMER_KEY, EpisodeTrace, compute_metrics, evaluate_heldout, write_plots
from export.tests.checkpoints import GOLDEN_DATASET, GOLDEN_REPO_ID
from export.tests.conftest import openapi_schema, requires_golden

RUN_ID = "00000000-0000-4000-8000-000000000002"
NORM = {
    "schema_version": "1",
    "eps": 1e-8,
    "features": {"action": {"type": "ACTION", "mode": "MEAN_STD", "mean": [0.0, 10.0], "std": [2.0, 4.0]}},
}


def _validate_eval(doc: dict[str, object]) -> None:
    import jsonschema

    jsonschema.Draft202012Validator(openapi_schema("EvalMetrics")).validate(doc)


def test_compute_metrics_exact_values() -> None:
    gt = np.array([[0.0, 10.0], [1.0, 10.0], [2.0, 10.0]], dtype=np.float32)
    pred = gt + np.array([[1.0, -2.0], [1.0, 2.0], [-1.0, 0.0]], dtype=np.float32)
    traces = [EpisodeTrace(3, pred[:2], gt[:2]), EpisodeTrace(7, pred[2:], gt[2:])]
    m = compute_metrics(traces, action_names=["a", "b"], run_id=RUN_ID, step=500, normalization=NORM)
    assert m["heldout_episodes"] == [3, 7] and m["n_frames"] == 3
    pj = {j["name"]: j for j in m["per_joint"]}
    assert pj["a"]["mae"] == pytest.approx(1.0) and pj["a"]["mse"] == pytest.approx(1.0)
    assert pj["b"]["mae"] == pytest.approx(4 / 3) and pj["b"]["mse"] == pytest.approx(8 / 3)
    assert m["overall"]["mae"] == pytest.approx((1 + 4 / 3) / 2)
    assert m["overall"]["mse"] == pytest.approx((1 + 8 / 3) / 2)
    # normalised: joint a errors /2, joint b errors /4
    assert m["overall"]["mae_normalized"] == pytest.approx(((1 / 2) + (4 / 3) / 4) / 2, rel=1e-6)
    assert m["disclaimer_key"] == DISCLAIMER_KEY
    _validate_eval(m)


def test_compute_metrics_edge_cases() -> None:
    with pytest.raises(ValueError):
        compute_metrics([], action_names=[], run_id=RUN_ID, step=1, normalization=None)
    t = EpisodeTrace(0, np.zeros((2, 3)), np.ones((2, 3)))
    m = compute_metrics([t], action_names=["only_one_name"], run_id=RUN_ID, step=1, normalization=None)
    assert m["action_names"] == ["joint_0", "joint_1", "joint_2"]
    assert "mae_normalized" not in m["overall"]


def test_write_plots(tmp_path: Path) -> None:
    rng = np.random.default_rng(0)
    traces = [EpisodeTrace(i, rng.normal(size=(40, 3)), rng.normal(size=(40, 3))) for i in range(12)]
    m = compute_metrics(traces, action_names=["x", "y", "z"], run_id=RUN_ID, step=9, normalization=None)
    entries = write_plots(traces, m, tmp_path / "plots", fps=30.0)
    assert len(entries) == 10  # spec: max 10 episode plots
    assert entries[0] == {"episode_index": 0, "path": "eval/plots/episode_000.png"}
    assert (tmp_path / "plots" / "per_joint_mae.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert all((tmp_path / "plots" / Path(e["path"]).name).is_file() for e in entries)
    single = [EpisodeTrace(5, rng.normal(size=(10, 1)), rng.normal(size=(10, 1)))]
    m1 = compute_metrics(single, action_names=["g"], run_id=RUN_ID, step=1, normalization=None)
    assert write_plots(single, m1, tmp_path / "p1", fps=10.0)[0]["path"] == "eval/plots/episode_005.png"


@requires_golden
def test_evaluate_heldout_on_golden_dataset(small_act: Path, tmp_path: Path) -> None:
    """Real select_action replay over a held-out episode of the golden dataset (CPU)."""
    m = evaluate_heldout(
        pretrained_dir=small_act,
        dataset_root=GOLDEN_DATASET,
        repo_id=GOLDEN_REPO_ID,
        heldout_episodes=[19],
        run_id=RUN_ID,
        step=1,
        out_dir=tmp_path / "eval",
    )
    from lerobot.datasets.lerobot_dataset import LeRobotDatasetMetadata

    meta = LeRobotDatasetMetadata(GOLDEN_REPO_ID, root=GOLDEN_DATASET)
    ep_len = int(meta.episodes[19]["length"])
    assert m["n_frames"] == ep_len
    assert m["action_names"][0] == "shoulder_pan.pos" and len(m["per_joint"]) == 6
    assert m["overall"]["mae"] > 0 and np.isfinite(m["overall"]["mse"])
    assert "mae_normalized" in m["overall"]
    assert m["plots"] == [{"episode_index": 19, "path": "eval/plots/episode_019.png"}]
    on_disk = json.loads((tmp_path / "eval" / "metrics.json").read_text())
    assert on_disk == m
    _validate_eval(on_disk)
    with pytest.raises(ValueError):
        evaluate_heldout(
            pretrained_dir=small_act,
            dataset_root=GOLDEN_DATASET,
            repo_id=GOLDEN_REPO_ID,
            heldout_episodes=[],
            run_id=RUN_ID,
            step=1,
        )
