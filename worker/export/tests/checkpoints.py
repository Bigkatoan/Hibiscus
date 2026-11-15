"""Test helpers: real LeRobot checkpoints (random-init, small) built against the golden dataset.

These are genuine ``save_pretrained`` outputs of LeRobot 0.7.1 (config.json, model.safetensors,
policy_pre/postprocessor + normalizer state from the dataset's stats) — only the weights are
untrained, which is irrelevant for export/parity/load tests.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

GOLDEN_DATASET = Path(
    os.environ.get(
        "HIBISCUS_GOLDEN_DATASET", str(Path.home() / "datasets/robotics/so101_picknplace_20261114")
    )
)
GOLDEN_REPO_ID = "local/so101_picknplace_20261114"
ACT_CHECKPOINT = Path(
    os.environ.get(
        "HIBISCUS_ACT_CHECKPOINT",
        str(Path.home() / "lelab/outputs/train/act_picknplace/checkpoints/010000/pretrained_model"),
    )
)
LELAB_PYTHON = Path(
    os.environ.get("HIBISCUS_LELAB_PYTHON", str(Path.home() / "lelab/leLab/.venv/bin/python"))
)
TRAIN_LOG = Path.home() / "lelab/outputs/train/act_picknplace.log"

SMALL_OVERRIDES: dict[str, dict[str, Any]] = {
    "act": {
        "dim_model": 64,
        "n_heads": 2,
        "dim_feedforward": 128,
        "n_encoder_layers": 1,
        "n_decoder_layers": 1,
        "n_vae_encoder_layers": 1,
        "chunk_size": 10,
        "n_action_steps": 5,
        "pretrained_backbone_weights": None,
    },
    "diffusion": {
        "n_obs_steps": 2,
        "horizon": 16,
        "n_action_steps": 8,
        "down_dims": (32, 64),
        "diffusion_step_embed_dim": 32,
        "crop_shape": (84, 84),
        "num_inference_steps": 10,
        "pretrained_backbone_weights": None,
        "spatial_softmax_num_keypoints": 8,
    },
    "vqbet": {
        "n_obs_steps": 3,
        "n_action_pred_token": 2,
        "action_chunk_size": 4,
        "gpt_n_layer": 1,
        "gpt_n_head": 2,
        "gpt_input_dim": 64,
        "gpt_output_dim": 64,
        "gpt_hidden_dim": 64,
        "vqvae_embedding_dim": 32,
        "vqvae_enc_hidden_dim": 32,
        "crop_shape": (84, 84),
        "pretrained_backbone_weights": None,
        "spatial_softmax_num_keypoints": 8,
    },
}


def make_random_checkpoint(
    policy_type: str,
    out_dir: Path,
    *,
    dataset_root: Path = GOLDEN_DATASET,
    repo_id: str = GOLDEN_REPO_ID,
    state_only: bool = False,
    **overrides: Any,
) -> Path:
    """``state_only`` drops camera inputs (e.g. TD-MPC only accepts square images)."""
    import torch
    from lerobot.configs.types import FeatureType
    from lerobot.datasets.lerobot_dataset import LeRobotDatasetMetadata
    from lerobot.policies.factory import (
        get_policy_class,
        make_policy,
        make_policy_config,
        make_pre_post_processors,
    )
    from lerobot.utils.feature_utils import dataset_to_policy_features

    torch.manual_seed(0)
    meta = LeRobotDatasetMetadata(repo_id, root=dataset_root)
    kwargs = {**SMALL_OVERRIDES.get(policy_type, {}), **overrides, "device": "cpu"}
    cfg = make_policy_config(policy_type, **kwargs)
    if state_only:
        feats = dataset_to_policy_features(meta.features)
        cfg.output_features = {k: f for k, f in feats.items() if f.type is FeatureType.ACTION}
        cfg.input_features = {k: f for k, f in feats.items() if f.type is FeatureType.STATE}
        policy = get_policy_class(policy_type)(cfg)
    else:
        policy = make_policy(cfg, ds_meta=meta)
    pre, post = make_pre_post_processors(cfg, dataset_stats=meta.stats)
    out_dir.mkdir(parents=True, exist_ok=True)
    policy.save_pretrained(out_dir)
    pre.save_pretrained(out_dir)
    post.save_pretrained(out_dir)
    return out_dir
