"""Shared worker helpers (owner A4), used by ``train``, ``validate`` (A3), ``export``/``eval`` (A5).

* :mod:`core.settings`   - ``WorkerSettings`` / ``get_settings()`` (env ``HIBISCUS_*``)
* :mod:`core.db`         - ``make_engine(url)``, ``with_retry(fn, budget_s=50)``
* :mod:`core.tables`     - SQLAlchemy Core mirror of the contract tables used by workers
* :mod:`core.s3`         - ``ObjectStore`` (upload/download dir/prefix, retries) + ``StorageError``
* :mod:`core.bus`        - Redis channel names, ``Bus.publish_run/publish_workspace``, ``sanitize``
* :mod:`core.events`     - ``Outbox``, ``append_run_event``, ``upsert_metrics``, ``transition``
* :mod:`core.jobs`       - generic ``jobs`` claim / heartbeat / finish (same lease protocol as runs)
* :mod:`core.export_api` - ``ExportContext`` / ``ExportOutcome`` hook for ``export.pipeline.run_export``
"""
