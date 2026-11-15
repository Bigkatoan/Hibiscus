from http import HTTPStatus
from typing import Any, Optional, Union

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.problem import Problem
from ...models.upload_session import UploadSession
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    body: Any,
    x_csrf_token: Union[Unset, str] = UNSET,
    idempotency_key: Union[Unset, str] = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_csrf_token, Unset):
        headers["X-CSRF-Token"] = x_csrf_token

    if not isinstance(idempotency_key, Unset):
        headers["Idempotency-Key"] = idempotency_key

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/uploads",
    }

    _kwargs["json"]: Any
    _kwargs["json"] = body

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[Problem, UploadSession]]:
    if response.status_code == 200:
        response_200 = UploadSession.from_dict(response.json())

        return response_200

    if response.status_code == 201:
        response_201 = UploadSession.from_dict(response.json())

        return response_201

    if response.status_code == 401:
        response_401 = Problem.from_dict(response.json())

        return response_401

    if response.status_code == 403:
        response_403 = Problem.from_dict(response.json())

        return response_403

    if response.status_code == 404:
        response_404 = Problem.from_dict(response.json())

        return response_404

    if response.status_code == 409:
        response_409 = Problem.from_dict(response.json())

        return response_409

    if response.status_code == 413:
        response_413 = Problem.from_dict(response.json())

        return response_413

    if response.status_code == 422:
        response_422 = Problem.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Response[Union[Problem, UploadSession]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: Any,
    x_csrf_token: Union[Unset, str] = UNSET,
    idempotency_key: Union[Unset, str] = UNSET,
) -> Response[Union[Problem, UploadSession]]:
    """Start a chunked upload of one archive

     Server fixes `part_size` (requested value clamped to [5 MiB, 64 MiB], default 64 MiB) and
    `part_count = ceil(size / part_size)`. Checks quota (`max_upload_bytes`, `storage_bytes`)
    up front (403 `quota_exceeded`). Honors `Idempotency-Key`. If an `active` session from the
    same user with identical (`workspace_id`, `sha256`, `size`) exists it is returned with 200
    instead of 201 (natural resume).

    Args:
        x_csrf_token (Union[Unset, str]):
        idempotency_key (Union[Unset, str]):
        body (Any): Exactly one of dataset_id (new version of an existing dataset) /
            new_dataset_name

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Problem, UploadSession]]
    """

    kwargs = _get_kwargs(
        body=body,
        x_csrf_token=x_csrf_token,
        idempotency_key=idempotency_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    body: Any,
    x_csrf_token: Union[Unset, str] = UNSET,
    idempotency_key: Union[Unset, str] = UNSET,
) -> Optional[Union[Problem, UploadSession]]:
    """Start a chunked upload of one archive

     Server fixes `part_size` (requested value clamped to [5 MiB, 64 MiB], default 64 MiB) and
    `part_count = ceil(size / part_size)`. Checks quota (`max_upload_bytes`, `storage_bytes`)
    up front (403 `quota_exceeded`). Honors `Idempotency-Key`. If an `active` session from the
    same user with identical (`workspace_id`, `sha256`, `size`) exists it is returned with 200
    instead of 201 (natural resume).

    Args:
        x_csrf_token (Union[Unset, str]):
        idempotency_key (Union[Unset, str]):
        body (Any): Exactly one of dataset_id (new version of an existing dataset) /
            new_dataset_name

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Problem, UploadSession]
    """

    return sync_detailed(
        client=client,
        body=body,
        x_csrf_token=x_csrf_token,
        idempotency_key=idempotency_key,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: Any,
    x_csrf_token: Union[Unset, str] = UNSET,
    idempotency_key: Union[Unset, str] = UNSET,
) -> Response[Union[Problem, UploadSession]]:
    """Start a chunked upload of one archive

     Server fixes `part_size` (requested value clamped to [5 MiB, 64 MiB], default 64 MiB) and
    `part_count = ceil(size / part_size)`. Checks quota (`max_upload_bytes`, `storage_bytes`)
    up front (403 `quota_exceeded`). Honors `Idempotency-Key`. If an `active` session from the
    same user with identical (`workspace_id`, `sha256`, `size`) exists it is returned with 200
    instead of 201 (natural resume).

    Args:
        x_csrf_token (Union[Unset, str]):
        idempotency_key (Union[Unset, str]):
        body (Any): Exactly one of dataset_id (new version of an existing dataset) /
            new_dataset_name

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Problem, UploadSession]]
    """

    kwargs = _get_kwargs(
        body=body,
        x_csrf_token=x_csrf_token,
        idempotency_key=idempotency_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: Any,
    x_csrf_token: Union[Unset, str] = UNSET,
    idempotency_key: Union[Unset, str] = UNSET,
) -> Optional[Union[Problem, UploadSession]]:
    """Start a chunked upload of one archive

     Server fixes `part_size` (requested value clamped to [5 MiB, 64 MiB], default 64 MiB) and
    `part_count = ceil(size / part_size)`. Checks quota (`max_upload_bytes`, `storage_bytes`)
    up front (403 `quota_exceeded`). Honors `Idempotency-Key`. If an `active` session from the
    same user with identical (`workspace_id`, `sha256`, `size`) exists it is returned with 200
    instead of 201 (natural resume).

    Args:
        x_csrf_token (Union[Unset, str]):
        idempotency_key (Union[Unset, str]):
        body (Any): Exactly one of dataset_id (new version of an existing dataset) /
            new_dataset_name

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Problem, UploadSession]
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
            x_csrf_token=x_csrf_token,
            idempotency_key=idempotency_key,
        )
    ).parsed
