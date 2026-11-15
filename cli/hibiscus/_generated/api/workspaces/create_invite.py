from http import HTTPStatus
from typing import Any, Optional, Union
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.invite_create import InviteCreate
from ...models.invite_created import InviteCreated
from ...models.problem import Problem
from ...types import UNSET, Response, Unset


def _get_kwargs(
    workspace_id: UUID,
    *,
    body: InviteCreate,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_csrf_token, Unset):
        headers["X-CSRF-Token"] = x_csrf_token

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/workspaces/{workspace_id}/invites".format(
            workspace_id=workspace_id,
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[InviteCreated, Problem]]:
    if response.status_code == 201:
        response_201 = InviteCreated.from_dict(response.json())

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

    if response.status_code == 422:
        response_422 = Problem.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Response[Union[InviteCreated, Problem]]:
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
    body: InviteCreate,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> Response[Union[InviteCreated, Problem]]:
    """Invite by email (72 h, single use). Returns `accept_url` only when email delivery is disabled.

    Args:
        workspace_id (UUID):
        x_csrf_token (Union[Unset, str]):
        body (InviteCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[InviteCreated, Problem]]
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
    client: AuthenticatedClient,
    body: InviteCreate,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> Optional[Union[InviteCreated, Problem]]:
    """Invite by email (72 h, single use). Returns `accept_url` only when email delivery is disabled.

    Args:
        workspace_id (UUID):
        x_csrf_token (Union[Unset, str]):
        body (InviteCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[InviteCreated, Problem]
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
    client: AuthenticatedClient,
    body: InviteCreate,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> Response[Union[InviteCreated, Problem]]:
    """Invite by email (72 h, single use). Returns `accept_url` only when email delivery is disabled.

    Args:
        workspace_id (UUID):
        x_csrf_token (Union[Unset, str]):
        body (InviteCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[InviteCreated, Problem]]
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
    client: AuthenticatedClient,
    body: InviteCreate,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> Optional[Union[InviteCreated, Problem]]:
    """Invite by email (72 h, single use). Returns `accept_url` only when email delivery is disabled.

    Args:
        workspace_id (UUID):
        x_csrf_token (Union[Unset, str]):
        body (InviteCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[InviteCreated, Problem]
    """

    return (
        await asyncio_detailed(
            workspace_id=workspace_id,
            client=client,
            body=body,
            x_csrf_token=x_csrf_token,
        )
    ).parsed
