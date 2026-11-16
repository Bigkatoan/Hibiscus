from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.list_run_events_response_200 import ListRunEventsResponse200
from ...models.problem import Problem
from ...models.run_event_type import RunEventType
from ...types import UNSET, Response, Unset


def _get_kwargs(
    run_id: UUID,
    *,
    after_seq: int | Unset = 0,
    types: list[RunEventType] | Unset = UNSET,
    limit: int | Unset = 200,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    params["after_seq"] = after_seq

    json_types: list[str] | Unset = UNSET
    if not isinstance(types, Unset):
        json_types = []
        for types_item_data in types:
            types_item = types_item_data.value
            json_types.append(types_item)

    params["types"] = json_types

    params["limit"] = limit

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/runs/{run_id}/events/history".format(
            run_id=quote(str(run_id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ListRunEventsResponse200 | Problem | None:
    if response.status_code == 200:
        response_200 = ListRunEventsResponse200.from_dict(response.json())

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
) -> Response[ListRunEventsResponse200 | Problem]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    run_id: UUID,
    *,
    client: AuthenticatedClient,
    after_seq: int | Unset = 0,
    types: list[RunEventType] | Unset = UNSET,
    limit: int | Unset = 200,
) -> Response[ListRunEventsResponse200 | Problem]:
    """Persisted run events as JSON (same payloads as SSE), ascending seq

    Args:
        run_id (UUID):
        after_seq (int | Unset):  Default: 0.
        types (list[RunEventType] | Unset):
        limit (int | Unset):  Default: 200.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ListRunEventsResponse200 | Problem]
    """

    kwargs = _get_kwargs(
        run_id=run_id,
        after_seq=after_seq,
        types=types,
        limit=limit,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    run_id: UUID,
    *,
    client: AuthenticatedClient,
    after_seq: int | Unset = 0,
    types: list[RunEventType] | Unset = UNSET,
    limit: int | Unset = 200,
) -> ListRunEventsResponse200 | Problem | None:
    """Persisted run events as JSON (same payloads as SSE), ascending seq

    Args:
        run_id (UUID):
        after_seq (int | Unset):  Default: 0.
        types (list[RunEventType] | Unset):
        limit (int | Unset):  Default: 200.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ListRunEventsResponse200 | Problem
    """

    return sync_detailed(
        run_id=run_id,
        client=client,
        after_seq=after_seq,
        types=types,
        limit=limit,
    ).parsed


async def asyncio_detailed(
    run_id: UUID,
    *,
    client: AuthenticatedClient,
    after_seq: int | Unset = 0,
    types: list[RunEventType] | Unset = UNSET,
    limit: int | Unset = 200,
) -> Response[ListRunEventsResponse200 | Problem]:
    """Persisted run events as JSON (same payloads as SSE), ascending seq

    Args:
        run_id (UUID):
        after_seq (int | Unset):  Default: 0.
        types (list[RunEventType] | Unset):
        limit (int | Unset):  Default: 200.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ListRunEventsResponse200 | Problem]
    """

    kwargs = _get_kwargs(
        run_id=run_id,
        after_seq=after_seq,
        types=types,
        limit=limit,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    run_id: UUID,
    *,
    client: AuthenticatedClient,
    after_seq: int | Unset = 0,
    types: list[RunEventType] | Unset = UNSET,
    limit: int | Unset = 200,
) -> ListRunEventsResponse200 | Problem | None:
    """Persisted run events as JSON (same payloads as SSE), ascending seq

    Args:
        run_id (UUID):
        after_seq (int | Unset):  Default: 0.
        types (list[RunEventType] | Unset):
        limit (int | Unset):  Default: 200.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ListRunEventsResponse200 | Problem
    """

    return (
        await asyncio_detailed(
            run_id=run_id,
            client=client,
            after_seq=after_seq,
            types=types,
            limit=limit,
        )
    ).parsed
