from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.problem import Problem
from ...models.workspace import Workspace
from ...models.workspace_create import WorkspaceCreate
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    body: WorkspaceCreate,
    x_csrf_token: str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_csrf_token, Unset):
        headers["X-CSRF-Token"] = x_csrf_token

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/workspaces",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Problem | Workspace | None:
    if response.status_code == 201:
        response_201 = Workspace.from_dict(response.json())

        return response_201

    if response.status_code == 401:
        response_401 = Problem.from_dict(response.json())

        return response_401

    if response.status_code == 403:
        response_403 = Problem.from_dict(response.json())

        return response_403

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
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Problem | Workspace]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: WorkspaceCreate,
    x_csrf_token: str | Unset = UNSET,
) -> Response[Problem | Workspace]:
    """Create a workspace (platform admins only in v1); creator becomes owner

    Args:
        x_csrf_token (str | Unset):
        body (WorkspaceCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | Workspace]
    """

    kwargs = _get_kwargs(
        body=body,
        x_csrf_token=x_csrf_token,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    body: WorkspaceCreate,
    x_csrf_token: str | Unset = UNSET,
) -> Problem | Workspace | None:
    """Create a workspace (platform admins only in v1); creator becomes owner

    Args:
        x_csrf_token (str | Unset):
        body (WorkspaceCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | Workspace
    """

    return sync_detailed(
        client=client,
        body=body,
        x_csrf_token=x_csrf_token,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: WorkspaceCreate,
    x_csrf_token: str | Unset = UNSET,
) -> Response[Problem | Workspace]:
    """Create a workspace (platform admins only in v1); creator becomes owner

    Args:
        x_csrf_token (str | Unset):
        body (WorkspaceCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | Workspace]
    """

    kwargs = _get_kwargs(
        body=body,
        x_csrf_token=x_csrf_token,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: WorkspaceCreate,
    x_csrf_token: str | Unset = UNSET,
) -> Problem | Workspace | None:
    """Create a workspace (platform admins only in v1); creator becomes owner

    Args:
        x_csrf_token (str | Unset):
        body (WorkspaceCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | Workspace
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
            x_csrf_token=x_csrf_token,
        )
    ).parsed
