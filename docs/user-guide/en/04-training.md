# 4. Training

*Primary (Vietnamese) version: `../vi/04-train.md`.*

## 4.1 The four-step wizard

1. **Dataset** — only *Ready* versions; **held-out episodes** default 10 % (2 of 20), used only for
   offline evaluation (chapter 5). 0 % = no offline evaluation.
2. **Policy** — cards greyed out with a reason when the dataset cannot support them. Start with **ACT**.
3. **Settings** — pick a **preset**, adjust if needed. *Basic* tab: the important fields with help
   and defaults; *Advanced*: every other `lerobot-train` option (LeRobot 0.7.1) with its CLI flag.
4. **Review and start** — changed settings, GPU (*Automatic* is fine), bundle options, **estimate**
   (GPU memory, time, queue; source shown) and **pre-start checks**. **Start training**.

Re-run with small changes: open the old run › **Copy settings to a new run**.

## 4.2 Policies

| Policy | When | GPUs | ONNX |
|---|---|---|---|
| **ACT** | First choice; few dozen demos; fast | RTX 3060, P40 | Yes |
| Diffusion Policy | Varied demonstrations | both | Yes (encoder + denoiser) |
| VQ-BeT | Multi-modal behaviour | both | Maybe in v1.1 |
| TD-MPC | Needs `next.reward` in the dataset | both | No |
| SmolVLA (~450M) | Follows task text; more memory | 3060 limited (bf16, small batch), P40 good | No |
| Pi0 / Pi0.5 (~3B) | Experimental, LoRA fine-tuning only | P40 only | No |

## 4.3 Presets

| Preset | Steps | Purpose | ACT on RTX 3060 (measured, batch 8) |
|---|---|---|---|
| Quick | 10,000 | Check data and settings | about 20 min |
| Standard | 100,000 | A real model | about 3 h |
| Fine-tune | 20,000 | Continue from a model / Hub checkpoint | depends |

Measured on the sample dataset (20 episodes, one 640×360 camera): ~0.11 s/step, ~1.8 GB VRAM.

## 4.4 Settings people change

Batch size (halve on out-of-memory) · training steps (loss flattens early; more steps ≠ better on
the robot) · checkpoint every N steps (pause/resume/export use checkpoints) · mixed precision
(`bf16` on the RTX 3060; **the Tesla P40 always runs fp32** — you get a warning, not an error) ·
image augmentation (lighting differs at run time) · ACT chunk size and actions per prediction
(the latter ≤ the former).

## 4.5 Queue and GPUs

Runs are ordered by priority, then **fair-share**. **GPU queue** shows positions and busy GPUs.
Default: one concurrent run per person. `cuda0` = RTX 3060 12 GB (bf16), `cuda1` = Tesla P40
24 GB (fp32, slower, more memory).

## 4.6 While training

Live status, step/total, ETA, next checkpoint, metrics, log, GPU. Statuses: Queued · Preparing ·
Running · Pausing/Paused · Building model · Succeeded/Failed/Cancelled. Watch the amber warnings:
loss NaN, no output for 5 min (stopped after 15), GPU memory > 95 %, automatic retry after a
server problem.

## 4.7 Pause, resume, cancel

* **Pause › At the next checkpoint** (recommended): trains until the next checkpoint (step and ETA
  shown), saves, frees the GPU; nothing lost.
* **Pause › Immediately**: progress since the last checkpoint is lost (no checkpoint yet ⇒ resume
  restarts at step 0 with the same seed).
* **Resume** re-queues and continues from the last checkpoint, possibly on the other GPU.
* **Cancel** stops for good; saved checkpoints can still be exported.
* Server-side failures are **retried once automatically** from the last checkpoint.

## 4.8 When a run fails

| Reason | Do |
|---|---|
| GPU out of memory | **Copy with half batch size**, or use the Tesla P40 |
| Loss became NaN repeatedly | **Copy with lower learning rate**; check the data for NaN |
| LeRobot rejected the settings | Read the log excerpt; **Copy and edit settings** |
| Worker lost / GPU error / stalled | **Resume** from the checkpoint |
| Monthly GPU hours used up | Run auto-paused; resume when quota is available |

## 4.9 Afterwards

Checkpoints tab (build a model or evaluate any checkpoint) · **Compare** 2–8 runs · the
**reproducibility manifest** (LeRobot/torch/CUDA versions, image, dataset fingerprint, full
settings, seed).
