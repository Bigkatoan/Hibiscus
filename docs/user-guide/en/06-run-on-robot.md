# 6. Running a model on the robot

*Primary (Vietnamese) version: `../vi/06-chay-tren-robot.md`.*

> **LeLab cannot run policies yet**, and Hibiscus does not modify LeLab. Run the model with the
> **LeRobot CLI** (`lerobot-rollout`) **inside the LeLab venv** (`~/lelab/leLab/.venv`, which
> already contains LeRobot 0.7.1) — nothing to install. When upstream LeLab gains policy running,
> the bundle will work there too because it is standard LeRobot.

## 6.1 Bundle contents

`pretrained_model/` (standard LeRobot policy folder for `--policy.path`) · `onnx/` (ACT, Diffusion)
· `eval/` · `logs/` · `run_on_robot.sh` · `MODEL_CARD.md` · `MANIFEST.json`. Get it with
**Download bundle (.zip)** or `hibiscus pull <model> --to ~/lelab/models`.

## 6.2 Safety first

Keep a hand near the arm's **power switch** the first time, clear the workspace, stay out of reach.
Start short: `DURATION=20 ./run_on_robot.sh`.

## 6.3 `run_on_robot.sh`

```bash
cd ~/lelab/models/so101_picknplace_act-r42-step100000
source ~/lelab/leLab/.venv/bin/activate
lerobot-find-port                 # follow the prompt: unplug USB, press Enter
lerobot-find-cameras opencv       # if you don't know the camera index
PORT=/dev/ttyACM0 ROBOT_ID=my_follower WRIST_CAM=0 ./run_on_robot.sh
```

The script is generated from the dataset (robot type, fps, camera names/resolution, first task)
and runs `lerobot-rollout --strategy.type=base --policy.path="$HERE/pretrained_model"
--robot.type=so101_follower --robot.port=$PORT --robot.id=$ROBOT_ID --robot.cameras="{ wrist_cam:
{…} }" --task="…" --fps=30 --duration=${DURATION:-60}`. Variables: `PORT`, `ROBOT_ID` (your
calibration id), one per camera (upper-cased camera name), `DURATION`. Camera names must match the
dataset (`observation.images.wrist_cam` ⇒ `wrist_cam`).

## 6.4 Other LeRobot commands

```bash
# run the policy and record evaluation episodes into a new dataset (LeRobot 0.7.1)
lerobot-rollout --strategy.type=episodic --policy.path=./pretrained_model \
  --robot.type=so101_follower --robot.port=/dev/ttyACM0 --robot.id=my_follower \
  --robot.cameras="{ wrist_cam: {type: opencv, index_or_path: 0, width: 640, height: 360, fps: 30} }" \
  --dataset.repo_id=<user>/eval_so101_picknplace --dataset.single_task="<task>" --dataset.num_episodes=10
```

In LeRobot 0.7.1 **`lerobot-record` has no `--policy` options**; policies run through
`lerobot-rollout`. After a Hub push, `--policy.path=<user>/<repo>` works too.

## 6.5 ONNX (no LeRobot needed)

ACT and Diffusion only (VQ-BeT maybe in v1.1). Use only when the ONNX badge says **parity passed**.

```bash
cd <bundle>/onnx && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python infer_onnx.py --bundle .. --selftest
```

`OnnxPolicy(bundle_dir)` with `.reset()` / `.select_action(obs)`; I/O described in `onnx/io_spec.json`.

## 6.6 Troubleshooting

| Symptom | Fix |
|---|---|
| `could not open port` | Wrong port or permissions: `lerobot-find-port`; add your user to `dialout`, log in again |
| LeRobot asks to calibrate | `ROBOT_ID` differs from your existing calibration id |
| Camera won't open | Wrong index (`lerobot-find-cameras opencv`); close LeLab/apps holding the camera |
| Missing feature `observation.images.<name>` | Camera name in the script differs from the dataset |
| Jerky or frozen robot | Lighting/camera pose differs from recording; behaviour quality depends on data (chapter 5) |
