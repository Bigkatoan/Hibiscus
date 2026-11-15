"""Thin hand-written layer over the generated client (``hibiscus._generated``).

* JSON operations go through the generated ``sync_detailed`` functions; error bodies
  (RFC 9457 ``Problem``) become :class:`ApiError` carrying the contract ``code``.
* Raw-byte operations the generator cannot express (``uploadPart`` octet-stream body,
  ``getModelFile`` / ``downloadModel`` binary + ``Range``, ``streamRunEvents`` SSE,
  ``getRunLogs`` text + ``Range``) use the same ``httpx.Client`` directly with the exact
  paths/headers of ``api/openapi.yaml``.
* Safe retries: idempotent requests are retried on transport errors, 5xx, 429 with
  exponential backoff (1, 2, 4 … 60 s, honouring ``Retry-After``).
"""

from __future__ import annotations

import json
import random
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, TypeVar
from uuid import UUID

import httpx

from hibiscus import __version__
from hibiscus._generated.api.auth import get_me
from hibiscus._generated.api.datasets import (
    get_dataset,
    list_dataset_versions,
    list_datasets,
)
from hibiscus._generated.api.models import get_model, list_model_files, list_models
from hibiscus._generated.api.policies import get_policy, list_policies
from hibiscus._generated.api.runs import create_run, get_run, list_runs, preflight_run
from hibiscus._generated.api.uploads import abort_upload, complete_upload, get_upload, init_upload
from hibiscus._generated.client import AuthenticatedClient
from hibiscus._generated.models.bundle_manifest import BundleManifest
from hibiscus._generated.models.dataset import Dataset
from hibiscus._generated.models.dataset_page import DatasetPage
from hibiscus._generated.models.dataset_version_page import DatasetVersionPage
from hibiscus._generated.models.list_policies_response_200 import ListPoliciesResponse200
from hibiscus._generated.models.me import Me
from hibiscus._generated.models.model import Model
from hibiscus._generated.models.model_page import ModelPage
from hibiscus._generated.models.policy_detail import PolicyDetail
from hibiscus._generated.models.policy_type import PolicyType
from hibiscus._generated.models.preflight_report import PreflightReport
from hibiscus._generated.models.problem import Problem
from hibiscus._generated.models.run import Run
from hibiscus._generated.models.run_create import RunCreate
from hibiscus._generated.models.run_page import RunPage
from hibiscus._generated.models.run_status import RunStatus
from hibiscus._generated.models.upload_completed import UploadCompleted
from hibiscus._generated.models.upload_session import UploadSession
from hibiscus._generated.types import UNSET, Response, Unset

T = TypeVar("T")

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504, 520, 521, 522, 523, 524})
USER_AGENT = f"hibiscus-cli/{__version__}"


@dataclass
class ApiError(Exception):
    """An error response from the API (or an unusable response)."""

    status: int
    code: str
    detail: str
    request_id: str | None = None
    missing_parts: list[int] = field(default_factory=list)
    retry_after_s: float | None = None
    body: dict[str, Any] | None = None

    def __str__(self) -> str:
        rid = f" (request id {self.request_id})" if self.request_id else ""
        return f"HTTP {self.status} {self.code}: {self.detail}{rid}"

    @classmethod
    def from_http(cls, status: int, content: bytes, headers: httpx.Headers) -> ApiError:
        body: dict[str, Any] | None = None
        try:
            parsed = json.loads(content.decode("utf-8")) if content else None
            if isinstance(parsed, dict):
                body = parsed
        except (UnicodeDecodeError, json.JSONDecodeError):
            body = None
        retry_after = _parse_retry_after(headers.get("Retry-After"))
        if body is not None and "code" in body:
            ra = body.get("retry_after_s")
            return cls(
                status=status,
                code=str(body.get("code")),
                detail=str(body.get("detail") or body.get("title") or ""),
                request_id=body.get("request_id") or headers.get("X-Request-Id"),
                missing_parts=[int(p) for p in body.get("missing_parts") or []],
                retry_after_s=float(ra) if isinstance(ra, (int, float)) else retry_after,
                body=body,
            )
        snippet = content[:200].decode("utf-8", "replace").strip()
        return cls(
            status=status,
            code=_fallback_code(status),
            detail=snippet or httpx.codes.get_reason_phrase(status),
            request_id=headers.get("X-Request-Id"),
            retry_after_s=retry_after,
        )

    @classmethod
    def from_problem(cls, problem: Problem, headers: httpx.Headers) -> ApiError:
        d = problem.to_dict()
        return cls.from_http(int(problem.status), json.dumps(d).encode(), headers)

    @property
    def retryable(self) -> bool:
        return self.status in RETRYABLE_STATUS


def _fallback_code(status: int) -> str:
    return {
        400: "bad_request",
        401: "unauthenticated",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        411: "length_required",
        413: "payload_too_large",
        416: "range_not_satisfiable",
        422: "validation_failed",
        429: "rate_limited",
        503: "service_unavailable",
    }.get(status, "internal_error" if status >= 500 else "bad_request")


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


@dataclass
class Backoff:
    """Exponential backoff 1, 2, 4 … ``cap`` seconds with ±20 % jitter (uploadPart contract)."""

    base: float = 1.0
    cap: float = 60.0
    attempts: int = 8
    sleep: Callable[[float], None] = time.sleep
    jitter: bool = True

    def delay(self, attempt: int, retry_after: float | None = None) -> float:
        d: float = min(self.cap, self.base * float(2**attempt))
        if self.jitter:
            d *= random.uniform(0.8, 1.2)  # noqa: S311 - jitter, not crypto
        if retry_after is not None:
            d = max(d, min(retry_after, self.cap * 5))
        return d


def is_transport_error(exc: BaseException) -> bool:
    return isinstance(exc, (httpx.TransportError, httpx.DecodingError))


class HibiscusApi:
    """Authenticated API session (PAT bearer) bound to one server and workspace."""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        workspace_id: str | None = None,
        timeout: float = 30.0,
        backoff: Backoff | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.workspace_id = workspace_id
        self.backoff = backoff or Backoff()
        self.http = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT},
            timeout=httpx.Timeout(timeout, connect=15.0),
            follow_redirects=False,
            transport=transport,
        )
        self._gen = AuthenticatedClient(base_url=self.base_url, token=token)
        self._gen.set_httpx_client(self.http)

    def close(self) -> None:
        self.http.close()

    def __enter__(self) -> HibiscusApi:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------------ helpers
    def ws(self) -> UUID:
        if not self.workspace_id:
            raise ApiError(0, "workspace_unknown", "no workspace configured; run `hibiscus login`")
        return UUID(self.workspace_id)

    def _call(self, fn: Callable[[], Response[Any]], expected: type[T], *, retry: bool = True) -> T:
        attempt = 0
        while True:
            try:
                resp = fn()
            except (ValueError, KeyError, TypeError) as exc:
                # generated parser rejected the body (e.g. unknown enum value from a newer server)
                raise ApiError(0, "bad_response", f"unexpected response shape: {exc}") from exc
            except Exception as exc:
                if retry and is_transport_error(exc) and attempt + 1 < self.backoff.attempts:
                    self.backoff.sleep(self.backoff.delay(attempt))
                    attempt += 1
                    continue
                raise
            parsed = resp.parsed
            if isinstance(parsed, expected) and 200 <= int(resp.status_code) < 300:
                return parsed
            if isinstance(parsed, Problem):
                err = ApiError.from_problem(parsed, httpx.Headers(dict(resp.headers)))
            else:
                err = ApiError.from_http(
                    int(resp.status_code), resp.content, httpx.Headers(dict(resp.headers))
                )
            if retry and err.retryable and attempt + 1 < self.backoff.attempts:
                self.backoff.sleep(self.backoff.delay(attempt, err.retry_after_s))
                attempt += 1
                continue
            raise err

    def request(
        self,
        method: str,
        url: str,
        *,
        retry: bool = True,
        expect: tuple[int, ...] = (200,),
        **kwargs: Any,
    ) -> httpx.Response:
        """Raw request with the same retry rules; raises ApiError for non-``expect`` statuses."""
        attempt = 0
        while True:
            try:
                resp = self.http.request(method, url, **kwargs)
            except Exception as exc:
                if retry and is_transport_error(exc) and attempt + 1 < self.backoff.attempts:
                    self.backoff.sleep(self.backoff.delay(attempt))
                    attempt += 1
                    continue
                raise
            if resp.status_code in expect:
                return resp
            err = ApiError.from_http(resp.status_code, resp.content, resp.headers)
            if retry and err.retryable and attempt + 1 < self.backoff.attempts:
                self.backoff.sleep(self.backoff.delay(attempt, err.retry_after_s))
                attempt += 1
                continue
            raise err

    @contextmanager
    def stream(self, method: str, url: str, **kwargs: Any) -> Iterator[httpx.Response]:
        with self.http.stream(method, url, **kwargs) as resp:
            yield resp

    # ------------------------------------------------------------------ auth
    def me(self) -> Me:
        return self._call(lambda: get_me.sync_detailed(client=self._gen), Me)

    # ------------------------------------------------------------------ datasets
    def list_datasets(self, q: str | None = None, limit: int = 50, cursor: str | None = None) -> DatasetPage:
        return self._call(
            lambda: list_datasets.sync_detailed(
                client=self._gen,
                workspace_id=self.ws(),
                q=q if q else UNSET,
                limit=limit,
                cursor=cursor if cursor else UNSET,
            ),
            DatasetPage,
        )

    def get_dataset(self, dataset_id: str) -> Dataset:
        return self._call(lambda: get_dataset.sync_detailed(UUID(dataset_id), client=self._gen), Dataset)

    def list_dataset_versions(
        self, dataset_id: str, limit: int = 50, cursor: str | None = None
    ) -> DatasetVersionPage:
        return self._call(
            lambda: list_dataset_versions.sync_detailed(
                UUID(dataset_id), client=self._gen, limit=limit, cursor=cursor if cursor else UNSET
            ),
            DatasetVersionPage,
        )

    def get_dataset_version(self, version_id: str) -> dict[str, Any]:
        """``GET /dataset-versions/{id}`` (getDatasetVersion) via the raw layer.

        The generated ``DatasetVersion`` model is unusable: openapi-python-client drops
        ``FeatureSpec`` (``names: {type: [array, object, 'null']}``) and leaves a dangling import
        (CONTRACT_NOTES change request CR-A9-1). Returns the JSON object.
        """
        resp = self.request("GET", f"/dataset-versions/{UUID(version_id)}")
        body = resp.json()
        if not isinstance(body, dict):
            raise ApiError(resp.status_code, "bad_response", "getDatasetVersion returned a non-object")
        return body

    # ------------------------------------------------------------------ uploads
    def init_upload(self, body: dict[str, Any], idempotency_key: str) -> UploadSession:
        # Idempotency-Key makes the POST safe to retry (contract: replay returns the original body)
        return self._call(
            lambda: init_upload.sync_detailed(client=self._gen, body=body, idempotency_key=idempotency_key),
            UploadSession,
        )

    def get_upload(self, upload_id: str) -> UploadSession:
        return self._call(lambda: get_upload.sync_detailed(UUID(upload_id), client=self._gen), UploadSession)

    def abort_upload(self, upload_id: str) -> None:
        resp = abort_upload.sync_detailed(UUID(upload_id), client=self._gen)
        if int(resp.status_code) != 204:
            raise ApiError.from_http(int(resp.status_code), resp.content, httpx.Headers(dict(resp.headers)))

    def upload_part(self, upload_id: str, part_number: int, data: bytes, sha256_hex: str) -> dict[str, Any]:
        """``PUT /uploads/{id}/parts/{n}`` (operationId uploadPart). Single attempt; caller retries."""
        resp = self.http.put(
            f"/uploads/{upload_id}/parts/{part_number}",
            content=data,
            headers={
                "Content-Type": "application/octet-stream",
                "X-Content-SHA256": sha256_hex,
                "Content-Length": str(len(data)),
            },
            timeout=httpx.Timeout(300.0, connect=15.0),
        )
        if resp.status_code != 200:
            raise ApiError.from_http(resp.status_code, resp.content, resp.headers)
        body = resp.json()
        if not isinstance(body, dict):
            raise ApiError(resp.status_code, "bad_response", "uploadPart returned a non-object")
        return body

    def complete_upload(self, upload_id: str) -> UploadCompleted:
        return self._call(
            lambda: complete_upload.sync_detailed(UUID(upload_id), client=self._gen), UploadCompleted
        )

    # ------------------------------------------------------------------ policies / runs
    def list_policies(self) -> ListPoliciesResponse200:
        return self._call(lambda: list_policies.sync_detailed(client=self._gen), ListPoliciesResponse200)

    def get_policy(self, policy_type: str) -> PolicyDetail:
        pt = PolicyType(policy_type)
        return self._call(lambda: get_policy.sync_detailed(pt, client=self._gen), PolicyDetail)

    def preflight(self, body: RunCreate) -> PreflightReport:
        return self._call(lambda: preflight_run.sync_detailed(client=self._gen, body=body), PreflightReport)

    def create_run(self, body: RunCreate, idempotency_key: str) -> Run:
        return self._call(
            lambda: create_run.sync_detailed(client=self._gen, body=body, idempotency_key=idempotency_key),
            Run,
        )

    def get_run(self, run_id: str) -> Run:
        return self._call(lambda: get_run.sync_detailed(UUID(run_id), client=self._gen), Run)

    def list_runs(
        self,
        *,
        status: list[str] | None = None,
        created_by: str | None = None,
        q: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> RunPage:
        st: list[RunStatus] | Unset = [RunStatus(s) for s in status] if status else UNSET
        return self._call(
            lambda: list_runs.sync_detailed(
                client=self._gen,
                workspace_id=self.ws(),
                status=st,
                created_by=created_by if created_by else UNSET,
                q=q if q else UNSET,
                limit=limit,
                cursor=cursor if cursor else UNSET,
            ),
            RunPage,
        )

    # ------------------------------------------------------------------ models
    def list_models(self, q: str | None = None, limit: int = 50, cursor: str | None = None) -> ModelPage:
        return self._call(
            lambda: list_models.sync_detailed(
                client=self._gen,
                workspace_id=self.ws(),
                q=q if q else UNSET,
                limit=limit,
                cursor=cursor if cursor else UNSET,
            ),
            ModelPage,
        )

    def get_model(self, model_id: str) -> Model:
        return self._call(lambda: get_model.sync_detailed(UUID(model_id), client=self._gen), Model)

    def list_model_files(self, model_id: str) -> BundleManifest:
        return self._call(
            lambda: list_model_files.sync_detailed(UUID(model_id), client=self._gen), BundleManifest
        )
