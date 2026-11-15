# lerobot-train 0.7.1 log parsing (contract v0.1)

Owner: A1 · Implementer: A4 (`worker/train/`). Normative regexes live in
[`worker/train/log_patterns.py`](../../worker/train/log_patterns.py); this document explains them.
Proof against a real log: `worker/train/tests/test_log_patterns.py` with fixture
`worker/train/tests/fixtures/act_picknplace.log.gz` (gzip of
`~/lelab/outputs/train/act_picknplace.log`, ACT, bs 8, `log_freq=200`,
`steps=100000`, killed at step 10123).

Run the proof:
```
cd worker && env -u PYTHONPATH uv run --no-project --python 3.12 --with pytest \
  python -m pytest -q -p no:cacheprovider train/tests -o addopts=""
```

## 1. Stream model

* The worker spawns `lerobot-train` with `stdout=PIPE, stderr=STDOUT` (single ordered stream),
  `PYTHONUNBUFFERED=1`, decodes UTF-8 with `errors="replace"`.
* tqdm (stderr, `desc="Training"`, `unit="step"`) rewrites its line with `\r` and **no** `\n`.
  Python logging lines end with `\n`. A logging line is frequently glued directly to the preceding
  tqdm frame (real bytes from the fixture):
  ```
  \rTraining:   0%|          | 200/100000 [00:26<3:01:01,  9.19step/s]INFO 2026-11-14 22:55:18 ot_train.py:894 step:200 smpl:2K ...\n
  ```
* Records = split on `[\r\n]` (`RECORD_SPLIT_RE`), keeping an incomplete trailing record in the
  buffer. ANSI escapes are stripped (`ANSI_RE`). Each record is scanned for progress matches
  (`TQDM_RE.finditer`) and for one log line starting at the first `INFO `/`WARNING `/`ERROR `/
  `CRITICAL `/`DEBUG ` occurrence (`LOG_LINE_RE.match(record, pos)`); matches are processed in
  positional order.

## 2. Line formats (verified in lerobot 0.7.1 source)

| Source | Format | Regex |
|---|---|---|
| `lerobot.utils.utils.init_logging` | `"%(levelname)s %(lerobot_pid)s%(asctime)s %(lerobot_location)15s %(message)s"`, `lerobot_location = f"{pathname}:{lineno}"[-15:]` (e.g. `ot_train.py:894`, right-aligned => may have leading spaces), `lerobot_pid = "[PID: n] "` only on non-main ranks | `LOG_PREFIX`, `LOG_LINE_RE` |
| `MetricsTracker.__str__` | `step:<big> smpl:<big> ep:<big> epch:<.2f> <meter> <meter> ...` with `<meter> = name:value` (`AverageMeter.__str__ = "{name}:{avg<fmt>}"`) | `METRICS_MSG_RE`, `METRIC_TOKEN_RE` |
| `format_big_number(n, precision=0)` | `f"{n:.0f}"` + `"" / K / M / B / T / Q` after dividing by 1000 => **rounded** (`4600 -> "5K"`, `1200 -> "1K"`, `1500 -> "2K"` banker's rounding) | `BIG_NUMBER`; exact re-implementation `format_big_number()` (cross-checked against lerobot's function: 0 mismatches over 48 572 values) |
| tqdm | `Training:  10%|█         | 10001/100000 [18:23<6:13:22,  4.02step/s]`; first frame `0/100000 [00:00<?, ?step/s]`; slow steps `5.14s/step` | `TQDM_RE` (`n`, `total`, `rate`, `rate_unit`) |
| header | `cfg.steps=100000 (100K)`, `dataset.num_frames=11277 (11K)`, `dataset.num_episodes=20`, `Effective batch size: 8 x 1 dp workers x 1 grad accum = 8 (...)`, `num_learnable_params=51597190 (52M)`, `Output dir: <path>` | `CFG_STEPS_RE`, `NUM_FRAMES_RE`, `NUM_EPISODES_RE`, `EFFECTIVE_BS_RE`, `LEARNABLE_PARAMS_RE`, `OUTPUT_DIR_RE` |
| training start | `Start offline training on a fixed dataset, with effective batch size: 8` | `TRAINING_START_RE` (=> status `running`) |
| checkpoint | `Checkpoint policy after step 10000` then `Model weights successfully saved to <dir>/pretrained_model!` | `CHECKPOINT_RE`, `CHECKPOINT_SAVED_RE` |
| eval split loss | `step 1000: eval_loss=0.1234` (only when `eval_steps > 0`, Hibiscus sets 0) | `EVAL_LOSS_RE` |
| end | `End of training` | `END_OF_TRAINING_RE` |
| failures | `torch.OutOfMemoryError` / `CUDA out of memory`; `Traceback (most recent call last):`; CUDA fatal; dataset errors | `OOM_RE`, `TRACEBACK_RE`, `NCCL_OR_CUDA_FATAL_RE`, `DATA_ERROR_RE` |

Meter names emitted in 0.7.1: `loss` (`:.3f`), `grdn` (`:.3f`), `lr` (`:0.1e`, e.g. `1.0e-05`),
`data_s`, `prep_s`, `updt_s`, `step_s` (`:.3f`), `smp/s` (`:.0f`), `scale` (fp16 only, `:.0f`),
`mem_gb` (CUDA only, `:.2f`), plus every numeric policy output key auto-registered with `:.3f`
(ACT: `l1_loss`, `kld_loss`; others vary). Values can be `nan`, `inf`, `-inf`.

## 3. Why the label is not the step

`step:5K` is `format_big_number(steps)`: the label for steps 4 600 … 5 400 is identical. `smpl` is
rounded the same way, and `epch` has only 2 decimals (`epch * num_frames / batch` is off by up to
±7 steps for this dataset, more for larger ones). Neither can produce the exact step. The fixture test asserts that steps 1000 and
1200 both carry label `1K` and 4600 / 5000 both carry `5K`.

## 4. Exact step resolution (normative)

lerobot logs exactly when `step % log_freq == 0`, where `step` starts at `initial_step` (0 for a
fresh run, `training_step.json.step` on resume) and increments by 1 per update. Therefore:

```
real_step(k-th metrics line) = (prev_step // log_freq + 1) * log_freq     # prev_step starts at initial_step
consistent = format_big_number(real_step) == step_label
             and (tqdm_step is None or real_step - log_freq < tqdm_step <= real_step)
tqdm_step  = initial_step + n   # n from the last TQDM_RE match before the log line
```

* `log_freq` is known: Hibiscus always passes `--log_freq` explicitly (train.json default 200).
* On resume tqdm restarts at `0/<steps - initial_step>`, hence `initial_step + n`.
* tqdm prints at most every `mininterval = 0.1 s`; for fast policies the frame for `n = real` may
  not precede the log line, so the cross-check allows `tqdm_step` in `(real - log_freq, real]`.
* `consistent == False` => store the metrics at `real_step` anyway and emit one `warning` run event
  `parser_mismatch` (rate-limited to 1 per 10 min) with `{label, tqdm_step, resolved}`. This only
  happens if lerobot's logging rule changes (caught by the golden E2E test on upgrade).
* Live progress (`progress` SSE event, `runs.current_step`) uses `tqdm_step` (monotonic max).

Real-log results asserted by the test: 50 metrics records at steps 200, 400, …, 10 000 (all
`consistent`), first record `loss 7.017, grad_norm 158.158, lr 1e-05, l1_loss 0.706,
kld_loss 0.631, gpu_mem_gb 1.79`, checkpoint at 10 000, last progress step 10 123, header
`steps=100000, num_frames=11277, num_episodes=20, effective_batch_size=8`.

## 5. Canonical metric keys (`run_metrics.key`, SSE `metrics.values`)

| Log token | Stored key | Unit |
|---|---|---|
| `loss` | `loss` | — |
| `grdn` | `grad_norm` | — |
| `lr` | `lr` | — |
| `data_s` | `data_s` | s (avg dataloading per step) |
| `prep_s` | `prep_s` | s |
| `updt_s` | `update_s` | s |
| `step_s` | `step_s` | s |
| `smp/s` | `samples_per_s` | samples/s |
| `scale` | `grad_scale` | — (fp16 only) |
| `mem_gb` | `gpu_mem_gb` | GB (torch peak, max over ranks) |
| any other `name` | lower-cased, `/` and `.` → `_`, must match `^[a-z][a-z0-9_]{0,63}$` else dropped | — |

Derived (computed by the worker, stored as metrics at the same step): `epoch` (from `epch` token,
2 decimals). NaN/Inf are stored as PG `double precision` NaN/Infinity and serialised as `null`
in JSON with `has_nonfinite=true`.

## 6. Anomaly rules tied to parsing

* Non-finite `loss` in a metrics record => `warning nan_detected`; 3 consecutive => SIGTERM,
  `error_code=nan_loss` (run-lifecycle §6).
* No bytes read from the pipe for 5 min => `warning log_silent` + notification `run.stalled`;
  15 min => kill, `error_code=stalled`. Checkpoint saves of large models are covered by the 15 min.
* `OOM_RE` anywhere => `error_code=oom` once the process exits.
* `gpu_mem_gb` > 0.95 × GPU VRAM (GB) => `warning vram_near_limit` (once per attempt).
