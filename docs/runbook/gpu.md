# GPU workers

## Mapping (ADR-0002: one container per GPU)

| Service | `device_ids` | GPU | Image | Precision |
|---|---|---|---|---|
| `worker-cuda0` | `0` | RTX 3060 12 GB, sm_86 | `hibiscus/worker-gpu` (torch 2.15.0, CUDA 13.2) | bf16/fp16/fp32 |
| `worker-cuda1` | `1` | Tesla P40 24 GB, sm_61 | `hibiscus/worker-gpu-pascal` (torch 2.14.1+cu126) | **fp32 only** (derived from the registered compute capability; `NVIDIA_TF32_OVERRIDE=0`) |
| `worker-cpu` | — | — | `hibiscus/worker-cpu` | validate / import / merge / hub push |

Device ids are NVIDIA indices in **PCI bus order** (= `nvidia-smi` order). On this box
`0000:01:00.0` is the 3060 and `0000:03:00.0` the P40 (`/proc/driver/nvidia/gpus/*/information`),
which matches the CUDA order the platform uses; images also set `CUDA_DEVICE_ORDER=PCI_BUS_ID`.
If a card is moved to another slot, pin by UUID instead: `HIBISCUS_GPU0_DEVICE=GPU-…` in
`deploy/.env` (UUIDs from the procfs files above).

Cgroup limits per GPU worker (override in `.env`): 4 CPUs, 11 GiB RAM, 8 GiB `/dev/shm`
(DataLoader workers), 4096 pids. Both GPU workers mount the same `cache` and `scratch` volumes at
`/cache` and `/scratch` (run-lifecycle §10). The P40 image exists because torch 2.15 wheels no
longer contain Pascal kernels (`torch.cuda.get_arch_list()` starts at `sm_75`); verify after any
rebuild:

```bash
docker run --rm -e CUDA_VISIBLE_DEVICES= hibiscus/worker-gpu-pascal:$TAG \
  python -c "import torch; print(torch.__version__, torch.cuda.get_arch_list())"   # must list sm_60
```

## Drain a GPU

Use the admin UI / API (`/admin/gpus`, sets `gpu_nodes.status = draining`): the worker finishes
its current run and claims nothing new. Then `docker compose --project-directory deploy stop
worker-cuda1`. Undrain: set `online`, `docker compose ... up -d worker-cuda1`.

## Adding a GPU

1. Install the card, confirm it in `/proc/driver/nvidia/gpus/` and note its index / UUID and
   compute capability.
2. Choose the image: sm_75+ → `worker-gpu`; sm_60–sm_70 → `worker-gpu-pascal`.
3. Copy the `worker-cuda1` block in `deploy/docker-compose.yml` to `worker-cuda2`: new
   `hostname`, `HIBISCUS_GPU_INDEX=2` (registers as `cuda2`), `HIBISCUS_NVML_INDEX=0` (the
   container sees only its own GPU), `device_ids`, memory limits. bf16/fp16 support is read
   from NVML at registration. Keep the shared `cache`/`scratch` mounts.
4. Add it to `GPU_WORKERS` in `deploy/scripts/check_compose.py` and to the `workers` scrape job
   in `deploy/observability/prometheus/prometheus.yml`.
5. Mind host RAM: 31 GB total; reduce `HIBISCUS_WORKER_GPU_MEMORY` if needed.
6. `make config && make up`; the worker registers its `gpu_nodes` row on start.

## P40 notes

No bf16, very slow fp16 → always fp32 (the scheduler also forces `--accelerator.mixed_precision=no`
and records the override, ADR-0002). Passive cooling: watch `HibiscusGpuTemperatureHigh`; the P40
needs case airflow. Pi0/Pi0.5 LoRA on the P40 stays `experimental` until the M3 smoke test.
