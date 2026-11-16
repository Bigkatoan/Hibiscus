from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.problem import Problem
from ...models.quota import Quota
from ...models.quota_upsert import QuotaUpsert
from ...types import UNSET, Response, Unset


def _get_kwargs(
    workspace_id: UUID,
    *,
    body: QuotaUpsert,
    x_csrf_token: str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_csrf_token, Unset):
        headers["X-CSRF-Token"] = x_csrf_token

    _kwargs: dict[str, Any] = {
        "method": "put",
        "url": "/admin/workspaces/{workspace_id}/quotas".format(
            workspace_id=quote(str(workspace_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Problem | Quota | None:
    if response.status_code == 200:
        response_200 = Quota.from_dict(response.json())

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

    if response.status_code == 422:
        response_422 = Problem.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Problem | Quota]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    workspace_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    body: QuotaUpsert,
    x_csrf_token: str | Unset = UNSET,
) -> Response[Problem | Quota]:
    """Create or replace the quota row for (workspace, user_id|null)

    Args:
        workspace_id (UUID):
        x_csrf_token (str | Unset):
        body (QuotaUpsert):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | Quota]
    """

    kwargs = _get_kwargs(
        workspace_id=workspace_id,
        body=body,
        x_csrf_token=x_csrf_token,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    workspace_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    body: QuotaUpsert,
    x_csrf_token: str | Unset = UNSET,
) -> Problem | Quota | None:
    """Create or replace the quota row for (workspace, user_id|null)

    Args:
        workspace_id (UUID):
        x_csrf_token (str | Unset):
        body (QuotaUpsert):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | Quota
    """

    return sync_detailed(
        workspace_id=workspace_id,
        client=client,
        body=body,
        x_csrf_token=x_csrf_token,
    ).parsed


async def asyncio_detailed(
    workspace_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    body: QuotaUpsert,
    x_csrf_token: str | Unset = UNSET,
) -> Response[Problem | Quota]:
    """Create or replace the quota row for (workspace, user_id|null)

    Args:
        workspace_id (UUID):
        x_csrf_token (str | Unset):
        body (QuotaUpsert):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | Quota]
    """

    kwargs = _get_kwargs(
        workspace_id=workspace_id,
        body=body,
        x_csrf_token=x_csrf_token,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    workspace_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    body: QuotaUpsert,
    x_csrf_token: str | Unset = UNSET,
) -> Problem | Quota | None:
    """Create or replace the quota row for (workspace, user_id|null)

    Args:
        workspace_id (UUID):
        x_csrf_token (str | Unset):
        body (QuotaUpsert):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | Quota
    """

    return (
        await asyncio_detailed(
            workspace_id=workspace_id,
            client=client,
            body=body,
            x_csrf_token=x_csrf_token,
        )
    ).parsed
