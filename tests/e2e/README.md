# tests/e2e/ (owner: A10 QC/QA)

Playwright E2E for every main flow and the golden E2E (PLAN §6): upload
`~/lelab/Picknplace_20261114_221710.rar` (RAR5, libarchive) → validate → train ACT
300 steps on a GPU → export → load with LeRobot + ONNX parity → download bundle. Golden dataset
reference: `~/datasets/robotics/so101_picknplace_20261114` (v3.0, 20 episodes,
`observation.images.wrist_cam` AV1 640x360, 6-dof `so_follower`).
