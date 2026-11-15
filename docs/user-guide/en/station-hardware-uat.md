# Hibiscus Station: hardware acceptance checklist (UAT)

Hibiscus Station was built and tested without any robot attached: every automated test runs on mock
motors, a mock leader, mock cameras and a tiny ACT policy. The items below can only be checked on a
real SO-101 (or SO-100) follower and leader. Run them once on your setup before relying on Station
for data collection, and again after a lerobot or firmware update.

Fill in the **Result** column (pass / fail / value) and keep this file with your lab notes. When an
item fails, open an issue with the session folder `~/.hibiscus/station/sessions/<id>/` attached
(it holds `session.json` and `telemetry.jsonl.gz`).

## 0. Before you start

* [ ] Power supply of the follower known (5 V, 7.4 V or 12 V kit): ______ V
* [ ] LeLab and every `lerobot-*` command closed (Station refuses a port another program holds).
* [ ] A thermometer (IR or probe) and a multimeter at hand.
* [ ] You can cut the arm's power by hand. The Station e-stop is software and never replaces this.
* [ ] Start Station: `hibiscus-station` (or `uvx hibiscus-station`). Note the version: ______

## 1. Ports, connection, calibration

| # | Check | How | Expected | Result |
|---|---|---|---|---|
| 1.1 | Port list | Robot screen, port picker | Only USB serial ports, with VID:PID; `/dev/serial/by-id/...` paths offered | |
| 1.2 | Find by unplugging | "Find by unplugging", unplug the follower USB | The follower port is found within 15 s | |
| 1.3 | Find by moving | "Find by moving", move the leader arm | The leader port is found within 10 s | |
| 1.4 | Port in use | Start `lerobot-teleoperate` on the follower, then Connect in Station | Clear error "Another program (LeLab? lerobot?) is using this port" | |
| 1.5 | Connect | Connect the profile | State `idle`, 6 motors on each arm, temperatures shown | |
| 1.6 | Calibrate follower | Calibrate screen: home, then ranges, then Finish | File written under `~/.cache/huggingface/lerobot/calibration/robots/so_follower/<id>.json`; `wrist_roll` marked full turn | |
| 1.7 | Calibrate leader | Same for the leader | File under `.../teleoperators/so_leader/<id>.json` | |
| 1.8 | Interop Station -> lerobot | `lerobot-teleoperate --robot.type=so101_follower --robot.id=<id> ...` with the Station files | Works without recalibration | |
| 1.9 | Interop lerobot/LeLab -> Station | Use a calibration made by lerobot or LeLab ("Use this calibration") | Positions look right in Station | |

## 2. Motor health telemetry (R1)

| # | Check | How | Expected | Result |
|---|---|---|---|---|
| 2.1 | Temperature unit | Compare a motor's Station value with the thermometer on its case after 10 min of teleop | Within ±2 °C (servo reads inside, may be warmer) | |
| 2.2 | Voltage unit | Multimeter on the bus supply vs Station `V` | Within ±0.2 V | |
| 2.3 | Current unit (6.5 mA/step, **unconfirmed**) | Stall the gripper on an object; compare with a clamp meter or bench supply reading | Same order of magnitude; note the ratio: ______ | |
| 2.4 | Load sign | Push a joint by hand both ways while torque is on | Load changes sign with the direction | |
| 2.5 | Status bits (**unconfirmed layout**) | Stall the gripper hard for several seconds | `overload` chip appears; Station stops the robot (critical) | |
| 2.6 | Leader voltage | Look at the leader voltage on a 5 V leader | No permanent voltage warning; if there is one, note `Min_Voltage_Limit`: ______ | |
| 2.7 | Limits read at connect | Health drawer tooltip | `Max_Temperature_Limit` shown (factory 70 °C) | |
| 2.8 | Loop timing with telemetry | Teleop 10 min at 30 Hz, then open the session summary | Overruns under 1 % of ticks, `telemetry_forced` small | |
| 2.9 | Read latency | `station.log` / session stats | p95 tick time under 36 ms at 30 Hz | |

## 3. Safety

| # | Check | How | Expected | Result |
|---|---|---|---|---|
| 3.1 | E-stop freeze | During teleop press Space (or the red button); film it with a phone at high frame rate | Arm freezes in under 100 ms, torque stays on, the arm does not fall | |
| 3.2 | E-stop relax | Press Space again within 2 s | Torque off (support the arm) | |
| 3.3 | Reset | "I'm clear, reset" | Back to idle | |
| 3.4 | Thermal stop | Settings: lower `temp_critical_c` to (current temperature + 1), keep the rules (hot ≤ critical − 3, warn ≤ hot − 5); teleop until it triggers | Red banner, hold, park at rest pose (if saved), torque off, state `estopped (thermal)`; reset refused while a motor is hot | |
| 3.5 | Rest pose | Robot screen: "Use current follower pose as rest pose", then trigger 3.4 again | The arm moves to the rest pose before torque goes off | |
| 3.6 | Dead-man | During a model run, close the browser tab | Robot freezes within about 1 s (`ui_lost`) | |
| 3.7 | Relative target cap | Run a model or replay with max relative target 2.0 | Movements are slowed; clipped joints are flagged in the joint panel | |
| 3.8 | USB unplug | Unplug the follower USB during teleop | State `error (bus_lost)`, no crash; reconnect works | |

## 4. Cameras (R2)

| # | Check | How | Expected | Result |
|---|---|---|---|---|
| 4.1 | Discover and probe | Cameras screen | Each camera listed once with a snapshot; measured fps shown | |
| 4.2 | Two cameras on one hub | Add two 640×480@30 MJPG cameras | Both stream; warning if measured fps < 90 % | |
| 4.3 | Previews during recording | Record an episode | All cameras visible during the whole recording | |
| 4.4 | Previews during a model run | Run model | All cameras visible, labelled "policy input", tick numbers advancing | |
| 4.5 | Camera unplug while recording | Unplug a camera during an episode | Alert; the episode clock pauses; after 3 s the session stops (`camera_lost`); the dataset stays valid | |

## 5. Recording and upload

| # | Check | How | Expected | Result |
|---|---|---|---|---|
| 5.1 | Record 3 episodes | Record with →, ←, Esc and one timeout | Dataset under `~/.hibiscus/station/datasets/<name>`; the timed-out episode is saved | |
| 5.2 | Dataset valid | `python -c "from pathlib import Path; from lerobot.datasets import LeRobotDataset as D; print(D('local/<name>', root=Path.home()/'.hibiscus/station/datasets/<name>'))"` | Loads; episode count right | |
| 5.3 | Telemetry sidecar | Datasets screen, episode temperature chart | One chart per episode; nothing inside the LeRobot folder | |
| 5.4 | Upload | Pair with your Hibiscus server, Upload | Dataset version created on the server; validation passes | |
| 5.5 | Upload resume | Pull the network cable during an upload, plug it back, upload again | Resumes from the parts already sent | |

## 6. Models on the robot

| # | Check | How | Expected | Result |
|---|---|---|---|---|
| 6.1 | Import a bundle | Run model: Import a `.zip` from Hibiscus | "verified" badge; compat checklist green | |
| 6.2 | Pull from server | "From server", then Pull | Model appears and loads; device and warm-up latency shown | |
| 6.3 | Run one episode | Run 1 episode of 20 s | Robot moves; inference latency p50/p95 shown; summary with max temperature per joint | |
| 6.4 | CPU too slow | Run a heavy policy on CPU at 30 fps | Session pauses with "model too slow" instead of queueing stale actions | |
| 6.5 | Evaluation recording | Run with "record evaluation dataset" | `eval_...` dataset saved and loadable | |

Sign-off: name ______  date ______  Station version ______  lerobot 0.7.1 commit `fe1c545`
