import datetime
from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.audit_action import AuditAction
from ...models.audit_event_page import AuditEventPage
from ...models.problem import Problem
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    workspace_id: UUID | Unset = UNSET,
    actor_user_id: UUID | Unset = UNSET,
    action: AuditAction | Unset = UNSET,
    since: datetime.datetime | Unset = UNSET,
    until: datetime.datetime | Unset = UNSET,
    limit: int | Unset = 50,
    cursor: str | Unset = UNSET,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    json_workspace_id: str | Unset = UNSET
    if not isinstance(workspace_id, Unset):
        json_workspace_id = str(workspace_id)
    params["workspace_id"] = json_workspace_id

    json_actor_user_id: str | Unset = UNSET
    if not isinstance(actor_user_id, Unset):
        json_actor_user_id = str(actor_user_id)
    params["actor_user_id"] = json_actor_user_id

    json_action: str | Unset = UNSET
    if not isinstance(action, Unset):
        json_action = action.value

    params["action"] = json_action

    json_since: str | Unset = UNSET
    if not isinstance(since, Unset):
        json_since = since.isoformat()
    params["since"] = json_since

    json_until: str | Unset = UNSET
    if not isinstance(until, Unset):
        json_until = until.isoformat()
    params["until"] = json_until

    params["limit"] = limit

    params["cursor"] = cursor

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/admin/audit-events",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> AuditEventPage | Problem | None:
    if response.status_code == 200:
        response_200 = AuditEventPage.from_dict(response.json())

        return response_200

    if response.status_code == 401:
        response_401 = Problem.from_dict(response.json())

        return response_401

    if response.status_code == 403:
        response_403 = Problem.from_dict(response.json())

        return response_403

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[AuditEventPage | Problem]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    workspace_id: UUID | Unset = UNSET,
    actor_user_id: UUID | Unset = UNSET,
    action: AuditAction | Unset = UNSET,
    since: datetime.datetime | Unset = UNSET,
    until: datetime.datetime | Unset = UNSET,
    limit: int | Unset = 50,
    cursor: str | Unset = UNSET,
) -> Response[AuditEventPage | Problem]:
    """Audit log, newest first

    Args:
        workspace_id (UUID | Unset):
        actor_user_id (UUID | Unset):
        action (AuditAction | Unset): Catalogue in docs/db-schema.md §Audit
        since (datetime.datetime | Unset):
        until (datetime.datetime | Unset):
        limit (int | Unset):  Default: 50.
        cursor (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AuditEventPage | Problem]
    """

    kwargs = _get_kwargs(
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        action=action,
        since=since,
        until=until,
        limit=limit,
        cursor=cursor,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    workspace_id: UUID | Unset = UNSET,
    actor_user_id: UUID | Unset = UNSET,
    action: AuditAction | Unset = UNSET,
    since: datetime.datetime | Unset = UNSET,
    until: datetime.datetime | Unset = UNSET,
    limit: int | Unset = 50,
    cursor: str | Unset = UNSET,
) -> AuditEventPage | Problem | None:
    """Audit log, newest first

    Args:
        workspace_id (UUID | Unset):
        actor_user_id (UUID | Unset):
        action (AuditAction | Unset): Catalogue in docs/db-schema.md §Audit
        since (datetime.datetime | Unset):
        until (datetime.datetime | Unset):
        limit (int | Unset):  Default: 50.
        cursor (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AuditEventPage | Problem
    """

    return sync_detailed(
        client=client,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        action=action,
        since=since,
        until=until,
        limit=limit,
        cursor=cursor,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    workspace_id: UUID | Unset = UNSET,
    actor_user_id: UUID | Unset = UNSET,
    action: AuditAction | Unset = UNSET,
    since: datetime.datetime | Unset = UNSET,
    until: datetime.datetime | Unset = UNSET,
    limit: int | Unset = 50,
    cursor: str | Unset = UNSET,
) -> Response[AuditEventPage | Problem]:
    """Audit log, newest first

    Args:
        workspace_id (UUID | Unset):
        actor_user_id (UUID | Unset):
        action (AuditAction | Unset): Catalogue in docs/db-schema.md §Audit
        since (datetime.datetime | Unset):
        until (datetime.datetime | Unset):
        limit (int | Unset):  Default: 50.
        cursor (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AuditEventPage | Problem]
    """

    kwargs = _get_kwargs(
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        action=action,
        since=since,
        until=until,
        limit=limit,
        cursor=cursor,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    workspace_id: UUID | Unset = UNSET,
    actor_user_id: UUID | Unset = UNSET,
    action: AuditAction | Unset = UNSET,
    since: datetime.datetime | Unset = UNSET,
    until: datetime.datetime | Unset = UNSET,
    limit: int | Unset = 50,
    cursor: str | Unset = UNSET,
) -> AuditEventPage | Problem | None:
    """Audit log, newest first

    Args:
        workspace_id (UUID | Unset):
        actor_user_id (UUID | Unset):
        action (AuditAction | Unset): Catalogue in docs/db-schema.md §Audit
        since (datetime.datetime | Unset):
        until (datetime.datetime | Unset):
        limit (int | Unset):  Default: 50.
        cursor (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AuditEventPage | Problem
    """

    return (
        await asyncio_detailed(
            client=client,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            action=action,
            since=since,
            until=until,
            limit=limit,
            cursor=cursor,
        )
    ).parsed
