from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.problem import Problem
from ...models.upload_page import UploadPage
from ...models.upload_status import UploadStatus
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    workspace_id: UUID,
    status: UploadStatus | Unset = UNSET,
    limit: int | Unset = 50,
    cursor: str | Unset = UNSET,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    json_workspace_id = str(workspace_id)
    params["workspace_id"] = json_workspace_id

    json_status: str | Unset = UNSET
    if not isinstance(status, Unset):
        json_status = status.value

    params["status"] = json_status

    params["limit"] = limit

    params["cursor"] = cursor

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/uploads",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Problem | UploadPage | None:
    if response.status_code == 200:
        response_200 = UploadPage.from_dict(response.json())

        return response_200

    if response.status_code == 401:
        response_401 = Problem.from_dict(response.json())

        return response_401

    if response.status_code == 403:
        response_403 = Problem.from_dict(response.json())

        return response_403

    if response.status_code == 404:
        response_404 = Problem.from_dict(response.json())

        return response_404

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Problem | UploadPage]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    workspace_id: UUID,
    status: UploadStatus | Unset = UNSET,
    limit: int | Unset = 50,
    cursor: str | Unset = UNSET,
) -> Response[Problem | UploadPage]:
    """Upload sessions of the caller in a workspace (newest first); used by the CLI to resume

    Args:
        workspace_id (UUID):
        status (UploadStatus | Unset):
        limit (int | Unset):  Default: 50.
        cursor (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | UploadPage]
    """

    kwargs = _get_kwargs(
        workspace_id=workspace_id,
        status=status,
        limit=limit,
        cursor=cursor,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    workspace_id: UUID,
    status: UploadStatus | Unset = UNSET,
    limit: int | Unset = 50,
    cursor: str | Unset = UNSET,
) -> Problem | UploadPage | None:
    """Upload sessions of the caller in a workspace (newest first); used by the CLI to resume

    Args:
        workspace_id (UUID):
        status (UploadStatus | Unset):
        limit (int | Unset):  Default: 50.
        cursor (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | UploadPage
    """

    return sync_detailed(
        client=client,
        workspace_id=workspace_id,
        status=status,
        limit=limit,
        cursor=cursor,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    workspace_id: UUID,
    status: UploadStatus | Unset = UNSET,
    limit: int | Unset = 50,
    cursor: str | Unset = UNSET,
) -> Response[Problem | UploadPage]:
    """Upload sessions of the caller in a workspace (newest first); used by the CLI to resume

    Args:
        workspace_id (UUID):
        status (UploadStatus | Unset):
        limit (int | Unset):  Default: 50.
        cursor (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | UploadPage]
    """

    kwargs = _get_kwargs(
        workspace_id=workspace_id,
        status=status,
        limit=limit,
        cursor=cursor,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    workspace_id: UUID,
    status: UploadStatus | Unset = UNSET,
    limit: int | Unset = 50,
    cursor: str | Unset = UNSET,
) -> Problem | UploadPage | None:
    """Upload sessions of the caller in a workspace (newest first); used by the CLI to resume

    Args:
        workspace_id (UUID):
        status (UploadStatus | Unset):
        limit (int | Unset):  Default: 50.
        cursor (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | UploadPage
    """

    return (
        await asyncio_detailed(
            client=client,
            workspace_id=workspace_id,
            status=status,
            limit=limit,
            cursor=cursor,
        )
    ).parsed
