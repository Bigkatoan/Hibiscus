from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.problem import Problem
from ...models.upload_part import UploadPart
from ...types import UNSET, Response, Unset


def _get_kwargs(
    upload_id: UUID,
    part_number: int,
    *,
    body: str,
    x_csrf_token: str | Unset = UNSET,
    x_content_sha256: str,
    content_length: int,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_csrf_token, Unset):
        headers["X-CSRF-Token"] = x_csrf_token

    headers["X-Content-SHA256"] = x_content_sha256

    headers["Content-Length"] = str(content_length)

    _kwargs: dict[str, Any] = {
        "method": "put",
        "url": "/uploads/{upload_id}/parts/{part_number}".format(
            upload_id=quote(str(upload_id), safe=""),
            part_number=quote(str(part_number), safe=""),
        ),
    }

    _kwargs["content"] = body.payload

    headers["Content-Type"] = "application/octet-stream"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Problem | UploadPart | None:
    if response.status_code == 200:
        response_200 = UploadPart.from_dict(response.json())

        return response_200

    if response.status_code == 401:
        response_401 = Problem.from_dict(response.json())

        return response_401

    if response.status_code == 404:
        response_404 = Problem.from_dict(response.json())

        return response_404

    if response.status_code == 409:
        response_409 = Problem.from_dict(response.json())

        return response_409

    if response.status_code == 411:
        response_411 = Problem.from_dict(response.json())

        return response_411

    if response.status_code == 413:
        response_413 = Problem.from_dict(response.json())

        return response_413

    if response.status_code == 422:
        response_422 = Problem.from_dict(response.json())

        return response_422

    if response.status_code == 429:
        response_429 = Problem.from_dict(response.json())

        return response_429

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Problem | UploadPart]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    upload_id: UUID,
    part_number: int,
    *,
    client: AuthenticatedClient,
    body: str,
    x_csrf_token: str | Unset = UNSET,
    x_content_sha256: str,
    content_length: int,
) -> Response[Problem | UploadPart]:
    """Upload one part (raw bytes). Re-uploading a part replaces it.

     Body is exactly `part_size` bytes for parts 1..N-1 and the remainder for part N
    (422 `upload_part_size_invalid` otherwise). The server streams the body to S3 UploadPart
    while hashing; if sha256 != `X-Content-SHA256` the part is discarded (422
    `upload_part_checksum_mismatch`). Each successful part slides `expires_at` to now + 7 days.
    Max body 64 MiB (fits Cloudflare's 100 MB limit). Recommended client timeout 300 s, retry
    with exponential backoff (1, 2, 4 ... 60 s) on network errors / 5xx / 429.

    Args:
        upload_id (UUID):
        part_number (int):
        x_csrf_token (str | Unset):
        x_content_sha256 (str):
        content_length (int):
        body (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | UploadPart]
    """

    kwargs = _get_kwargs(
        upload_id=upload_id,
        part_number=part_number,
        body=body,
        x_csrf_token=x_csrf_token,
        x_content_sha256=x_content_sha256,
        content_length=content_length,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    upload_id: UUID,
    part_number: int,
    *,
    client: AuthenticatedClient,
    body: str,
    x_csrf_token: str | Unset = UNSET,
    x_content_sha256: str,
    content_length: int,
) -> Problem | UploadPart | None:
    """Upload one part (raw bytes). Re-uploading a part replaces it.

     Body is exactly `part_size` bytes for parts 1..N-1 and the remainder for part N
    (422 `upload_part_size_invalid` otherwise). The server streams the body to S3 UploadPart
    while hashing; if sha256 != `X-Content-SHA256` the part is discarded (422
    `upload_part_checksum_mismatch`). Each successful part slides `expires_at` to now + 7 days.
    Max body 64 MiB (fits Cloudflare's 100 MB limit). Recommended client timeout 300 s, retry
    with exponential backoff (1, 2, 4 ... 60 s) on network errors / 5xx / 429.

    Args:
        upload_id (UUID):
        part_number (int):
        x_csrf_token (str | Unset):
        x_content_sha256 (str):
        content_length (int):
        body (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | UploadPart
    """

    return sync_detailed(
        upload_id=upload_id,
        part_number=part_number,
        client=client,
        body=body,
        x_csrf_token=x_csrf_token,
        x_content_sha256=x_content_sha256,
        content_length=content_length,
    ).parsed


async def asyncio_detailed(
    upload_id: UUID,
    part_number: int,
    *,
    client: AuthenticatedClient,
    body: str,
    x_csrf_token: str | Unset = UNSET,
    x_content_sha256: str,
    content_length: int,
) -> Response[Problem | UploadPart]:
    """Upload one part (raw bytes). Re-uploading a part replaces it.

     Body is exactly `part_size` bytes for parts 1..N-1 and the remainder for part N
    (422 `upload_part_size_invalid` otherwise). The server streams the body to S3 UploadPart
    while hashing; if sha256 != `X-Content-SHA256` the part is discarded (422
    `upload_part_checksum_mismatch`). Each successful part slides `expires_at` to now + 7 days.
    Max body 64 MiB (fits Cloudflare's 100 MB limit). Recommended client timeout 300 s, retry
    with exponential backoff (1, 2, 4 ... 60 s) on network errors / 5xx / 429.

    Args:
        upload_id (UUID):
        part_number (int):
        x_csrf_token (str | Unset):
        x_content_sha256 (str):
        content_length (int):
        body (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | UploadPart]
    """

    kwargs = _get_kwargs(
        upload_id=upload_id,
        part_number=part_number,
        body=body,
        x_csrf_token=x_csrf_token,
        x_content_sha256=x_content_sha256,
        content_length=content_length,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    upload_id: UUID,
    part_number: int,
    *,
    client: AuthenticatedClient,
    body: str,
    x_csrf_token: str | Unset = UNSET,
    x_content_sha256: str,
    content_length: int,
) -> Problem | UploadPart | None:
    """Upload one part (raw bytes). Re-uploading a part replaces it.

     Body is exactly `part_size` bytes for parts 1..N-1 and the remainder for part N
    (422 `upload_part_size_invalid` otherwise). The server streams the body to S3 UploadPart
    while hashing; if sha256 != `X-Content-SHA256` the part is discarded (422
    `upload_part_checksum_mismatch`). Each successful part slides `expires_at` to now + 7 days.
    Max body 64 MiB (fits Cloudflare's 100 MB limit). Recommended client timeout 300 s, retry
    with exponential backoff (1, 2, 4 ... 60 s) on network errors / 5xx / 429.

    Args:
        upload_id (UUID):
        part_number (int):
        x_csrf_token (str | Unset):
        x_content_sha256 (str):
        content_length (int):
        body (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | UploadPart
    """

    return (
        await asyncio_detailed(
            upload_id=upload_id,
            part_number=part_number,
            client=client,
            body=body,
            x_csrf_token=x_csrf_token,
            x_content_sha256=x_content_sha256,
            content_length=content_length,
        )
    ).parsed
