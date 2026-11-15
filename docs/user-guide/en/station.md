# Hibiscus Station: the robot-side app

Hibiscus Station runs on the computer the robot is plugged into. It replaces the LeLab workflow:
connect the arms, calibrate, add cameras, teleoperate, record a LeRobot dataset, upload it to your
Hibiscus workspace, train on the server, pull the trained model and run it on the robot.

Two things it adds over LeLab:

* **Motor health.** Every motor's temperature, voltage, current, load and alarm flags are shown on
  every screen that moves the robot. A motor that gets warm is shown in yellow (50 °C), hot in orange
  (60 °C: no new session can start), critical in red (65 °C twice in a row, or an overheat/overload
  alarm). On critical, Station holds the arm, parks it at your rest pose if you saved one, and turns
  the torque off before the servo's own 70 °C cutoff would drop it.
* **Cameras while a model runs.** The Run-model screen shows every camera live, with the exact
  frames the model receives, next to the joint positions, the commanded actions, the motor
  temperatures, the speed (FPS) and the inference time. Cameras are also shown during teleop,
  recording and replay.

## Install

You need [uv](https://docs.astral.sh/uv/). Then:

```bash
# Station is not on PyPI yet: install the wheel from GitHub Releases (UI included)
uv tool install https://github.com/Bigkatoan/Hibiscus/releases/latest/download/hibiscus_station-0.1.0-py3-none-any.whl
hibiscus-station
```

Station starts on `http://127.0.0.1:18210` and opens your browser. It only accepts connections from
the same computer. If the browser does not open, run `hibiscus-station url` and open the link it
prints. To try it without a robot: `hibiscus-station --mock`.

Close LeLab and any `lerobot-*` command first: only one program can use a serial port.

## The steps

1. **Robot.** Create a profile: robot type, follower port, leader port (optional). "Find by
   unplugging" and "Find by moving" help you pick the right port. Connect. You now see the joint
   positions and motor temperatures. Use "Use current follower pose as rest pose" once the arm is in
   a safe folded pose: Station parks there before turning the torque off.
2. **Calibrate.** For each arm: move every joint to the middle of its range, press *Set home*, then
   move each joint through its whole range and press *Finish*. Calibration files are stored where
   lerobot keeps them, so LeLab and `lerobot-*` commands can use them too. Existing files can be
   reused with *Use this calibration*.
3. **Cameras.** Add the discovered cameras. Their names (`wrist`, `front`, ...) are the names models
   will expect (`observation.images.<name>`).
4. **Teleop.** Move the leader, the follower follows. If the leader is far from the follower pose,
   Station asks you to bring it closer first.
5. **Record.** Choose a dataset name, the task sentence, the number of episodes and their length.
   Keys: **→** next (save and continue), **←** re-record, **Esc** stop. An episode that reaches its
   time limit is saved (unlike LeLab, which silently re-records it); you can change that to
   *discard*.
6. **Upload.** Pair Station with your Hibiscus server once (server URL and a personal access token
   with `datasets:write` and `models:read`; add `runs:read` to see runs). Then upload the dataset as
   a new dataset or a new version. Uploads resume after a network loss.
7. **Train.** "Open training on Hibiscus" opens the server's New Run page. Training runs on the
   server, never on the robot computer.
8. **Run model.** Import a bundle zip or a `pretrained_model` folder, or pull a model from the
   server. Station checks that it fits your robot (joints, camera names and resolutions) and offers
   fixes. Load it, set the task and episode length, and start.

## Safety

* **E-stop:** the big red button or the **Space** key. First press: the arm freezes and keeps its
  torque. Second press within 2 s (or *Relax*): torque off, so hold the arm. *I'm clear, reset*
  returns to idle.
* While a model runs, the browser must stay open: if Station stops hearing from it for 1 s, the
  robot freezes.
* Movements are limited per step (`max relative target`, 5 degrees by default).
* The e-stop is software. Keep a way to cut the robot's power by hand.

## Where things are

`~/.hibiscus/station/` holds the robot profiles (`robots.yaml`), settings, datasets
(`datasets/<name>/`, a normal LeRobot dataset, with motor telemetry next to it in
`datasets/<name>.hibiscus/`), models (`models/`) and session logs (`sessions/`). The server token
is stored by the Hibiscus CLI (system keyring), never in that folder.

Before relying on Station, run the hardware checklist: [station-hardware-uat.md](station-hardware-uat.md).
