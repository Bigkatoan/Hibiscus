"""``python -m train``: the GPU worker.

The worker image runs ``python -m $HIBISCUS_WORKER_MODULE`` with ``train`` as the default. Compose
marks the CPU worker with ``HIBISCUS_WORKER_KIND=cpu``; that worker must run the dataset validator
(``python -m validate``), so dispatch on it here too (QC-e2e-03: with the default module the CPU
worker ran the GPU loop and never validated a dataset).
"""

import os

if os.environ.get("HIBISCUS_WORKER_KIND", "").strip().lower() == "cpu":
    from validate.runner import main
else:
    from train.worker import main

main()
