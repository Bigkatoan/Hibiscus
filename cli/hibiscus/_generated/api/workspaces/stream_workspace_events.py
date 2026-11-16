from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.problem import Problem
from ...models.workspace_stream_event import WorkspaceStreamEvent
from ...types import Response


def _get_kwargs(
    workspace_id: UUID,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/workspaces/{workspace_id}/events".format(
            workspace_id=quote(str(workspace_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Problem | WorkspaceStreamEvent | None:
    if response.status_code == 200:
        response_200 = WorkspaceStreamEvent.from_dict(response.text)

        return response_200

    if response.status_code == 401:
        response_401 = Problem.from_dict(response.json())

        return response_401

    if response.status_code == 404:
        response_404 = Problem.from_dict(response.json())

        return response_404

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Problem | WorkspaceStreamEvent]:
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
) -> Response[Problem | WorkspaceStreamEvent]:
    """SSE stream of workspace-level changes (run status, dataset status, model ready, notifications)

     Ephemeral stream (no replay); `event:` is one of `WorkspaceStreamEvent.event`. Heartbeat every 15 s.
    The session and workspace membership are re-checked every 15 s: the stream ends when the
    session is revoked / logged out or the membership ends, and after at most 15 min in any
    case (the client reconnects with fresh credentials; CR-BE-S1).

    Args:
        workspace_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | WorkspaceStreamEvent]
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
    client: AuthenticatedClient | Client,
) -> Problem | WorkspaceStreamEvent | None:
    """SSE stream of workspace-level changes (run status, dataset status, model ready, notifications)

     Ephemeral stream (no replay); `event:` is one of `WorkspaceStreamEvent.event`. Heartbeat every 15 s.
    The session and workspace membership are re-checked every 15 s: the stream ends when the
    session is revoked / logged out or the membership ends, and after at most 15 min in any
    case (the client reconnects with fresh credentials; CR-BE-S1).

    Args:
        workspace_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | WorkspaceStreamEvent
    """

    return sync_detailed(
        workspace_id=workspace_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    workspace_id: UUID,
    *,
    client: AuthenticatedClient | Client,
) -> Response[Problem | WorkspaceStreamEvent]:
    """SSE stream of workspace-level changes (run status, dataset status, model ready, notifications)

     Ephemeral stream (no replay); `event:` is one of `WorkspaceStreamEvent.event`. Heartbeat every 15 s.
    The session and workspace membership are re-checked every 15 s: the stream ends when the
    session is revoked / logged out or the membership ends, and after at most 15 min in any
    case (the client reconnects with fresh credentials; CR-BE-S1).

    Args:
        workspace_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | WorkspaceStreamEvent]
    """

    kwargs = _get_kwargs(
        workspace_id=workspace_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    workspace_id: UUID,
    *,
    client: AuthenticatedClient | Client,
) -> Problem | WorkspaceStreamEvent | None:
    """SSE stream of workspace-level changes (run status, dataset status, model ready, notifications)

     Ephemeral stream (no replay); `event:` is one of `WorkspaceStreamEvent.event`. Heartbeat every 15 s.
    The session and workspace membership are re-checked every 15 s: the stream ends when the
    session is revoked / logged out or the membership ends, and after at most 15 min in any
    case (the client reconnects with fresh credentials; CR-BE-S1).

    Args:
        workspace_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | WorkspaceStreamEvent
    """

    return (
        await asyncio_detailed(
            workspace_id=workspace_id,
            client=client,
        )
    ).parsed
