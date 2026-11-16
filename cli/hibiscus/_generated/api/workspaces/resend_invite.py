from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.invite_created import InviteCreated
from ...models.problem import Problem
from ...types import UNSET, Response, Unset


def _get_kwargs(
    workspace_id: UUID,
    invite_id: UUID,
    *,
    x_csrf_token: str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_csrf_token, Unset):
        headers["X-CSRF-Token"] = x_csrf_token

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/workspaces/{workspace_id}/invites/{invite_id}/resend".format(
            workspace_id=quote(str(workspace_id), safe=""),
            invite_id=quote(str(invite_id), safe=""),
        ),
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> InviteCreated | Problem | None:
    if response.status_code == 200:
        response_200 = InviteCreated.from_dict(response.json())

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

    if response.status_code == 429:
        response_429 = Problem.from_dict(response.json())

        return response_429

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[InviteCreated | Problem]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    workspace_id: UUID,
    invite_id: UUID,
    *,
    client: AuthenticatedClient,
    x_csrf_token: str | Unset = UNSET,
) -> Response[InviteCreated | Problem]:
    """Re-issue the token (new 72 h window, old link invalid) and re-send

    Args:
        workspace_id (UUID):
        invite_id (UUID):
        x_csrf_token (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[InviteCreated | Problem]
    """

    kwargs = _get_kwargs(
        workspace_id=workspace_id,
        invite_id=invite_id,
        x_csrf_token=x_csrf_token,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    workspace_id: UUID,
    invite_id: UUID,
    *,
    client: AuthenticatedClient,
    x_csrf_token: str | Unset = UNSET,
) -> InviteCreated | Problem | None:
    """Re-issue the token (new 72 h window, old link invalid) and re-send

    Args:
        workspace_id (UUID):
        invite_id (UUID):
        x_csrf_token (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        InviteCreated | Problem
    """

    return sync_detailed(
        workspace_id=workspace_id,
        invite_id=invite_id,
        client=client,
        x_csrf_token=x_csrf_token,
    ).parsed


async def asyncio_detailed(
    workspace_id: UUID,
    invite_id: UUID,
    *,
    client: AuthenticatedClient,
    x_csrf_token: str | Unset = UNSET,
) -> Response[InviteCreated | Problem]:
    """Re-issue the token (new 72 h window, old link invalid) and re-send

    Args:
        workspace_id (UUID):
        invite_id (UUID):
        x_csrf_token (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[InviteCreated | Problem]
    """

    kwargs = _get_kwargs(
        workspace_id=workspace_id,
        invite_id=invite_id,
        x_csrf_token=x_csrf_token,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    workspace_id: UUID,
    invite_id: UUID,
    *,
    client: AuthenticatedClient,
    x_csrf_token: str | Unset = UNSET,
) -> InviteCreated | Problem | None:
    """Re-issue the token (new 72 h window, old link invalid) and re-send

    Args:
        workspace_id (UUID):
        invite_id (UUID):
        x_csrf_token (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        InviteCreated | Problem
    """

    return (
        await asyncio_detailed(
            workspace_id=workspace_id,
            invite_id=invite_id,
            client=client,
            x_csrf_token=x_csrf_token,
        )
    ).parsed
