from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.list_invites_response_200 import ListInvitesResponse200
from ...models.problem import Problem
from ...types import Response


def _get_kwargs(
    workspace_id: UUID,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/workspaces/{workspace_id}/invites".format(
            workspace_id=quote(str(workspace_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ListInvitesResponse200 | Problem | None:
    if response.status_code == 200:
        response_200 = ListInvitesResponse200.from_dict(response.json())

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
) -> Response[ListInvitesResponse200 | Problem]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    workspace_id: UUID,
    *,
    client: AuthenticatedClient,
) -> Response[ListInvitesResponse200 | Problem]:
    """Pending invites (owner, admin), newest first

    Args:
        workspace_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ListInvitesResponse200 | Problem]
    """

    kwargs = _get_kwargs(
        workspace_id=workspace_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    workspace_id: UUID,
    *,
    client: AuthenticatedClient,
) -> ListInvitesResponse200 | Problem | None:
    """Pending invites (owner, admin), newest first

    Args:
        workspace_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ListInvitesResponse200 | Problem
    """

    return sync_detailed(
        workspace_id=workspace_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    workspace_id: UUID,
    *,
    client: AuthenticatedClient,
) -> Response[ListInvitesResponse200 | Problem]:
    """Pending invites (owner, admin), newest first

    Args:
        workspace_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ListInvitesResponse200 | Problem]
    """

    kwargs = _get_kwargs(
        workspace_id=workspace_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    workspace_id: UUID,
    *,
    client: AuthenticatedClient,
) -> ListInvitesResponse200 | Problem | None:
    """Pending invites (owner, admin), newest first

    Args:
        workspace_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ListInvitesResponse200 | Problem
    """

    return (
        await asyncio_detailed(
            workspace_id=workspace_id,
            client=client,
        )
    ).parsed
