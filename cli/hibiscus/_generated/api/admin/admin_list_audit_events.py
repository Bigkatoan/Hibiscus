import datetime
from http import HTTPStatus
from typing import Any, Optional, Union
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
    workspace_id: Union[Unset, UUID] = UNSET,
    actor_user_id: Union[Unset, UUID] = UNSET,
    action: Union[Unset, AuditAction] = UNSET,
    since: Union[Unset, datetime.datetime] = UNSET,
    until: Union[Unset, datetime.datetime] = UNSET,
    limit: Union[Unset, int] = 50,
    cursor: Union[Unset, str] = UNSET,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    json_workspace_id: Union[Unset, str] = UNSET
    if not isinstance(workspace_id, Unset):
        json_workspace_id = str(workspace_id)
    params["workspace_id"] = json_workspace_id

    json_actor_user_id: Union[Unset, str] = UNSET
    if not isinstance(actor_user_id, Unset):
        json_actor_user_id = str(actor_user_id)
    params["actor_user_id"] = json_actor_user_id

    json_action: Union[Unset, str] = UNSET
    if not isinstance(action, Unset):
        json_action = action.value

    params["action"] = json_action

    json_since: Union[Unset, str] = UNSET
    if not isinstance(since, Unset):
        json_since = since.isoformat()
    params["since"] = json_since

    json_until: Union[Unset, str] = UNSET
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
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[AuditEventPage, Problem]]:
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
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Response[Union[AuditEventPage, Problem]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: Union[AuthenticatedClient, Client],
    workspace_id: Union[Unset, UUID] = UNSET,
    actor_user_id: Union[Unset, UUID] = UNSET,
    action: Union[Unset, AuditAction] = UNSET,
    since: Union[Unset, datetime.datetime] = UNSET,
    until: Union[Unset, datetime.datetime] = UNSET,
    limit: Union[Unset, int] = 50,
    cursor: Union[Unset, str] = UNSET,
) -> Response[Union[AuditEventPage, Problem]]:
    """Audit log, newest first

    Args:
        workspace_id (Union[Unset, UUID]):
        actor_user_id (Union[Unset, UUID]):
        action (Union[Unset, AuditAction]): Catalogue in docs/db-schema.md §Audit
        since (Union[Unset, datetime.datetime]):
        until (Union[Unset, datetime.datetime]):
        limit (Union[Unset, int]):  Default: 50.
        cursor (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[AuditEventPage, Problem]]
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
    client: Union[AuthenticatedClient, Client],
    workspace_id: Union[Unset, UUID] = UNSET,
    actor_user_id: Union[Unset, UUID] = UNSET,
    action: Union[Unset, AuditAction] = UNSET,
    since: Union[Unset, datetime.datetime] = UNSET,
    until: Union[Unset, datetime.datetime] = UNSET,
    limit: Union[Unset, int] = 50,
    cursor: Union[Unset, str] = UNSET,
) -> Optional[Union[AuditEventPage, Problem]]:
    """Audit log, newest first

    Args:
        workspace_id (Union[Unset, UUID]):
        actor_user_id (Union[Unset, UUID]):
        action (Union[Unset, AuditAction]): Catalogue in docs/db-schema.md §Audit
        since (Union[Unset, datetime.datetime]):
        until (Union[Unset, datetime.datetime]):
        limit (Union[Unset, int]):  Default: 50.
        cursor (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[AuditEventPage, Problem]
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
    client: Union[AuthenticatedClient, Client],
    workspace_id: Union[Unset, UUID] = UNSET,
    actor_user_id: Union[Unset, UUID] = UNSET,
    action: Union[Unset, AuditAction] = UNSET,
    since: Union[Unset, datetime.datetime] = UNSET,
    until: Union[Unset, datetime.datetime] = UNSET,
    limit: Union[Unset, int] = 50,
    cursor: Union[Unset, str] = UNSET,
) -> Response[Union[AuditEventPage, Problem]]:
    """Audit log, newest first

    Args:
        workspace_id (Union[Unset, UUID]):
        actor_user_id (Union[Unset, UUID]):
        action (Union[Unset, AuditAction]): Catalogue in docs/db-schema.md §Audit
        since (Union[Unset, datetime.datetime]):
        until (Union[Unset, datetime.datetime]):
        limit (Union[Unset, int]):  Default: 50.
        cursor (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[AuditEventPage, Problem]]
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
    client: Union[AuthenticatedClient, Client],
    workspace_id: Union[Unset, UUID] = UNSET,
    actor_user_id: Union[Unset, UUID] = UNSET,
    action: Union[Unset, AuditAction] = UNSET,
    since: Union[Unset, datetime.datetime] = UNSET,
    until: Union[Unset, datetime.datetime] = UNSET,
    limit: Union[Unset, int] = 50,
    cursor: Union[Unset, str] = UNSET,
) -> Optional[Union[AuditEventPage, Problem]]:
    """Audit log, newest first

    Args:
        workspace_id (Union[Unset, UUID]):
        actor_user_id (Union[Unset, UUID]):
        action (Union[Unset, AuditAction]): Catalogue in docs/db-schema.md §Audit
        since (Union[Unset, datetime.datetime]):
        until (Union[Unset, datetime.datetime]):
        limit (Union[Unset, int]):  Default: 50.
        cursor (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[AuditEventPage, Problem]
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
