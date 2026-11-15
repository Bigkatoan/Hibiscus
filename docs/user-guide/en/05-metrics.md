# 5. Reading metrics honestly

*Primary (Vietnamese) version: `../vi/05-doc-metrics.md`.*

> **No number in Hibiscus is the robot's success rate.** Low loss, low offline error and the
> "Verified" badge can all belong to a model that fails on the real robot. The only way to know
> is to **run it on the robot** (chapter 6) and count successes.

## 5.1 Training loss

* Measures how well the model fits the **training data**. If training works, it **always** goes down —
  so a falling loss proves *training runs*, not *the robot will succeed*. The model can memorise
  demonstrations and still fail when the object moves a little.
* Real example (ACT, 20-episode sample dataset, RTX 3060): 7.0 at step 200 → 2.5 at 600 → 0.166 at
  10,000. Normal, and silent about pick-and-place success.
* ACT: `loss = l1_loss + kl_weight × kld_loss` (default `kl_weight` = 10). `l1_loss` is the
  normalised action error on training data; `kld_loss` is the VAE term, usually near 0.
* Flat is normal; short spikes are normal; **steady climb or NaN** = learning rate too high or bad data.
* Compare losses **only between runs with the same dataset and policy**.

## 5.2 Other metrics

Gradient norm (huge spikes before NaN → lower the learning rate) · learning rate (check the
schedule) · throughput (drops usually mean data loading; see data-loading time per step) · peak GPU
memory (close to the limit → OOM risk) · GPU tab (low utilisation → CPU/video decoding bottleneck).

## 5.3 Offline evaluation on held-out episodes

Episodes held out before training (default 10 %, recorded in the manifest) are replayed: the model
predicts an action for every frame and it is compared with the **recorded** action. You get
MAE/MSE per joint and overall in the dataset's action units (SO-101: motor position units, not
millimetres) and predicted-vs-recorded plots.

* Use it to **compare** checkpoints or runs on the **same dataset**, and to spot joints learnt badly.
* Don't use it as a promise: it measures step-by-step imitation on old data; on the robot small
  errors compound over hundreds of steps, objects move, lighting changes.
* With 20 episodes, 10 % is 2 episodes — noisy. Don't over-read small differences.

## 5.4 "Verified"

Technically correct bundle: (1) loads in LeRobot and predicts a valid action, (2) every file matches
`MANIFEST.json`, (3) ONNX matches PyTorch when exported. Nothing about behaviour quality.

## 5.5 Recommended loop

Quick preset → Standard → use offline error to pick the best candidate → **test on the robot**
(e.g. 10 trials, varied object positions) → if poor, record more varied demonstrations (data
usually matters more than hyperparameters), upload as a new version, copy the run onto it.
