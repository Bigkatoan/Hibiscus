# 8. Troubleshooting

*Primary (Vietnamese) version: `../vi/08-xu-ly-su-co.md`.*

Every error in Hibiscus has a title, an explanation and what to do; the full list (vi + en) is
`docs/ux/error-catalogue.md`. When reporting a problem, include the **Request ID** (copy button
next to the message) and the run number (e.g. `#42`).

| Situation | Do |
|---|---|
| "Session ended" | Sign in again; wizard input is kept |
| "Security check failed" on sign-in | Reload; disable VPN/ad blocker if it repeats |
| "The page's security token is outdated" | Reload (often after signing in on another tab) |
| "Not found" | Deleted, or in a workspace you're not a member of |
| Charts frozen, "Connection lost, reconnecting…" | Wait; reload if it persists. Training is **not** affected |
| Upload stopped | Reopen the upload page and choose the same file; CLI: rerun the same command |
| "File too large" / "Quota reached" | Split and merge later, delete old data, or ask an admin |
| Dataset "Invalid" | Validation tab lists episode and fix (chapter 2.3) |
| Run waits a long time | GPU queue: both GPUs busy, or you already have a run going |
| "Not enough GPU memory" before start | Smaller batch, gradient checkpointing/LoRA, or the Tesla P40 |
| Run failed | Read "Why the run failed" and use the suggested button (chapter 4.8) |
| Model "Not verified" because ONNX failed | Don't use `onnx/`; `pretrained_model/` still works with LeRobot |
| Robot does nothing / errors | Chapter 6.6 |
| Verified, low offline error, robot still fails | It happens (chapter 5): more varied demos, another checkpoint, same camera/lighting as recording |
