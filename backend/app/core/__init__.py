"""Shared backend core (owner A2, OWNERSHIP.md note 1). Stable module API used by every package:

* ``app.core.errors``: ``ErrorCode`` (contract catalogue), ``ProblemError(status, code, detail=None, **ext)``.
* ``app.core.deps``: ``get_db``, ``current_principal`` -> ``Principal`` (``user_id``,
  ``workspace_ids_roles``, ``auth_method``, ``token_scopes``, ``token_workspace_id``,
  ``mfa_verified``), ``session_principal``, ``require_scope(scope)``,
  ``require_role(workspace_id, min_role)``, ``ensure_role(principal, workspace_id, min_role)``,
  ``platform_admin``, ``services(request)``.
* ``app.core.pagination``: ``encode_cursor(dict) -> str``, ``decode_cursor(str) -> dict``.
* ``app.core.storage``: ``S3`` (``put_part``, ``complete_multipart``, ``stream_object(range)``, ...),
  ``BUCKET_UPLOADS`` / ``BUCKET_DATASETS`` / ``BUCKET_ARTIFACTS``.
* ``app.core.events``: ``publish_run_event(run_id, event, data, persist, *, db=None)``,
  ``publish_workspace_event``.
* ``app.core.audit``: ``AuditAction``, ``record(action, *, db, actor, workspace_id, target_type,
  target_id, details)``.
* ``app.core.email``: ``EmailSender`` protocol + cloudflare / smtp / none providers.
* ``app.core.settings``: ``Settings`` / ``get_settings()``; ``app.core.logging``; ``app.core.ratelimit``.
"""
