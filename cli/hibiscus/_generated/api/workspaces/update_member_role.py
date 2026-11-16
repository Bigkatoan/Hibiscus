from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.member import Member
from ...models.problem import Problem
from ...models.update_member_role_body import UpdateMemberRoleBody
from ...types import UNSET, Response, Unset


def _get_kwargs(
    workspace_id: UUID,
    user_id: UUID,
    *,
    body: UpdateMemberRoleBody,
    x_csrf_token: str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_csrf_token, Unset):
        headers["X-CSRF-Token"] = x_csrf_token

    _kwargs: dict[str, Any] = {
        "method": "patch",
        "url": "/workspaces/{workspace_id}/members/{user_id}".format(
            workspace_id=quote(str(workspace_id), safe=""),
            user_id=quote(str(user_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Member | Problem | None:
    if response.status_code == 200:
        response_200 = Member.from_dict(response.json())

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

    if response.status_code == 409:
        response_409 = Problem.from_dict(response.json())

        return response_409

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Member | Problem]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    workspace_id: UUID,
    user_id: UUID,
    *,
    client: AuthenticatedClient,
    body: UpdateMemberRoleBody,
    x_csrf_token: str | Unset = UNSET,
) -> Response[Member | Problem]:
    """Change a member's role

     owner can set any role; admin can set member/viewer for non-owners. Demoting the last
    owner => 409 `last_owner`. Promoting to owner/admin requires the target to have 2FA
    enabled (409 `mfa_required_by_role`).

    Args:
        workspace_id (UUID):
        user_id (UUID):
        x_csrf_token (str | Unset):
        body (UpdateMemberRoleBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Member | Problem]
    """

    kwargs = _get_kwargs(
        workspace_id=workspace_id,
        user_id=user_id,
        body=body,
        x_csrf_token=x_csrf_token,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    workspace_id: UUID,
    user_id: UUID,
    *,
    client: AuthenticatedClient,
    body: UpdateMemberRoleBody,
    x_csrf_token: str | Unset = UNSET,
) -> Member | Problem | None:
    """Change a member's role

     owner can set any role; admin can set member/viewer for non-owners. Demoting the last
    owner => 409 `last_owner`. Promoting to owner/admin requires the target to have 2FA
    enabled (409 `mfa_required_by_role`).

    Args:
        workspace_id (UUID):
        user_id (UUID):
        x_csrf_token (str | Unset):
        body (UpdateMemberRoleBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Member | Problem
    """

    return sync_detailed(
        workspace_id=workspace_id,
        user_id=user_id,
        client=client,
        body=body,
        x_csrf_token=x_csrf_token,
    ).parsed


async def asyncio_detailed(
    workspace_id: UUID,
    user_id: UUID,
    *,
    client: AuthenticatedClient,
    body: UpdateMemberRoleBody,
    x_csrf_token: str | Unset = UNSET,
) -> Response[Member | Problem]:
    """Change a member's role

     owner can set any role; admin can set member/viewer for non-owners. Demoting the last
    owner => 409 `last_owner`. Promoting to owner/admin requires the target to have 2FA
    enabled (409 `mfa_required_by_role`).

    Args:
        workspace_id (UUID):
        user_id (UUID):
        x_csrf_token (str | Unset):
        body (UpdateMemberRoleBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Member | Problem]
    """

    kwargs = _get_kwargs(
        workspace_id=workspace_id,
        user_id=user_id,
        body=body,
        x_csrf_token=x_csrf_token,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    workspace_id: UUID,
    user_id: UUID,
    *,
    client: AuthenticatedClient,
    body: UpdateMemberRoleBody,
    x_csrf_token: str | Unset = UNSET,
) -> Member | Problem | None:
    """Change a member's role

     owner can set any role; admin can set member/viewer for non-owners. Demoting the last
    owner => 409 `last_owner`. Promoting to owner/admin requires the target to have 2FA
    enabled (409 `mfa_required_by_role`).

    Args:
        workspace_id (UUID):
        user_id (UUID):
        x_csrf_token (str | Unset):
        body (UpdateMemberRoleBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Member | Problem
    """

    return (
        await asyncio_detailed(
            workspace_id=workspace_id,
            user_id=user_id,
            client=client,
            body=body,
            x_csrf_token=x_csrf_token,
        )
    ).parsed
