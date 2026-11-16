from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.problem import Problem
from ...models.upload_completed import UploadCompleted
from ...types import UNSET, Response, Unset


def _get_kwargs(
    upload_id: UUID,
    *,
    x_csrf_token: str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_csrf_token, Unset):
        headers["X-CSRF-Token"] = x_csrf_token

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/uploads/{upload_id}/complete".format(
            upload_id=quote(str(upload_id), safe=""),
        ),
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Problem | UploadCompleted | None:
    if response.status_code == 202:
        response_202 = UploadCompleted.from_dict(response.json())

        return response_202

    if response.status_code == 401:
        response_401 = Problem.from_dict(response.json())

        return response_401

    if response.status_code == 404:
        response_404 = Problem.from_dict(response.json())

        return response_404

    if response.status_code == 409:
        response_409 = Problem.from_dict(response.json())

        return response_409

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Problem | UploadCompleted]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    upload_id: UUID,
    *,
    client: AuthenticatedClient,
    x_csrf_token: str | Unset = UNSET,
) -> Response[Problem | UploadCompleted]:
    """Finish the multipart upload and queue unpack + validation

     Requires every part 1..part_count (409 `upload_incomplete` with `missing_parts`). Server
    calls S3 CompleteMultipartUpload, creates the `DatasetVersion` (status `pending`, creating
    the dataset first when `new_dataset_name` was given) and queues a `validate_dataset` job
    whose first step re-hashes the whole object and compares with the declared `sha256`
    (mismatch => version `failed`, code `upload_checksum_mismatch`). Idempotent: calling again
    on a completed session returns the same body.

    Args:
        upload_id (UUID):
        x_csrf_token (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | UploadCompleted]
    """

    kwargs = _get_kwargs(
        upload_id=upload_id,
        x_csrf_token=x_csrf_token,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    upload_id: UUID,
    *,
    client: AuthenticatedClient,
    x_csrf_token: str | Unset = UNSET,
) -> Problem | UploadCompleted | None:
    """Finish the multipart upload and queue unpack + validation

     Requires every part 1..part_count (409 `upload_incomplete` with `missing_parts`). Server
    calls S3 CompleteMultipartUpload, creates the `DatasetVersion` (status `pending`, creating
    the dataset first when `new_dataset_name` was given) and queues a `validate_dataset` job
    whose first step re-hashes the whole object and compares with the declared `sha256`
    (mismatch => version `failed`, code `upload_checksum_mismatch`). Idempotent: calling again
    on a completed session returns the same body.

    Args:
        upload_id (UUID):
        x_csrf_token (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | UploadCompleted
    """

    return sync_detailed(
        upload_id=upload_id,
        client=client,
        x_csrf_token=x_csrf_token,
    ).parsed


async def asyncio_detailed(
    upload_id: UUID,
    *,
    client: AuthenticatedClient,
    x_csrf_token: str | Unset = UNSET,
) -> Response[Problem | UploadCompleted]:
    """Finish the multipart upload and queue unpack + validation

     Requires every part 1..part_count (409 `upload_incomplete` with `missing_parts`). Server
    calls S3 CompleteMultipartUpload, creates the `DatasetVersion` (status `pending`, creating
    the dataset first when `new_dataset_name` was given) and queues a `validate_dataset` job
    whose first step re-hashes the whole object and compares with the declared `sha256`
    (mismatch => version `failed`, code `upload_checksum_mismatch`). Idempotent: calling again
    on a completed session returns the same body.

    Args:
        upload_id (UUID):
        x_csrf_token (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | UploadCompleted]
    """

    kwargs = _get_kwargs(
        upload_id=upload_id,
        x_csrf_token=x_csrf_token,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    upload_id: UUID,
    *,
    client: AuthenticatedClient,
    x_csrf_token: str | Unset = UNSET,
) -> Problem | UploadCompleted | None:
    """Finish the multipart upload and queue unpack + validation

     Requires every part 1..part_count (409 `upload_incomplete` with `missing_parts`). Server
    calls S3 CompleteMultipartUpload, creates the `DatasetVersion` (status `pending`, creating
    the dataset first when `new_dataset_name` was given) and queues a `validate_dataset` job
    whose first step re-hashes the whole object and compares with the declared `sha256`
    (mismatch => version `failed`, code `upload_checksum_mismatch`). Idempotent: calling again
    on a completed session returns the same body.

    Args:
        upload_id (UUID):
        x_csrf_token (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | UploadCompleted
    """

    return (
        await asyncio_detailed(
            upload_id=upload_id,
            client=client,
            x_csrf_token=x_csrf_token,
        )
    ).parsed
