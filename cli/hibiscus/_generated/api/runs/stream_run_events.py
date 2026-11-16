from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.problem import Problem
from ...models.run_stream_event import RunStreamEvent
from ...models.stream_run_events_include_item import StreamRunEventsIncludeItem
from ...types import UNSET, Response, Unset


def _get_kwargs(
    run_id: UUID,
    *,
    after_seq: int | Unset = UNSET,
    include: list[StreamRunEventsIncludeItem] | Unset = UNSET,
    last_event_id: str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(last_event_id, Unset):
        headers["Last-Event-ID"] = last_event_id

    params: dict[str, Any] = {}

    params["after_seq"] = after_seq

    json_include: list[str] | Unset = UNSET
    if not isinstance(include, Unset):
        json_include = []
        for include_item_data in include:
            include_item = include_item_data.value
            json_include.append(include_item)

    params["include"] = json_include

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/runs/{run_id}/events".format(
            run_id=quote(str(run_id), safe=""),
        ),
        "params": params,
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Problem | RunStreamEvent | None:
    if response.status_code == 200:
        response_200 = RunStreamEvent.from_dict(response.text)

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
) -> Response[Problem | RunStreamEvent]:
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
    after_seq: int | Unset = UNSET,
    include: list[StreamRunEventsIncludeItem] | Unset = UNSET,
    last_event_id: str | Unset = UNSET,
) -> Response[Problem | RunStreamEvent]:
    """Live run stream (SSE). See RunStreamEvent for framing.

     Framing (one SSE message per event):
    ```
    id: 42            # only for persisted events (= run_events.seq)
    event: metrics    # RunStreamEvent.event
    data: {...}       # JSON, schema by event name (RunStreamEvent oneOf)
    ```
    * `retry: 3000` is sent first. `event: heartbeat` every 15 s (Cloudflare idles at ~100 s).
    * The caller's session / PAT and workspace membership are re-checked every 15 s; the stream
      ends (no `end` event) when either is gone, and after at most 15 min in any case - the
      client reconnects with `Last-Event-ID` (CR-BE-S1).
    * With `Last-Event-ID: <seq>` (or `?after_seq=`) the server first replays persisted events
      with seq > N (status, metrics, checkpoint, warning, error, model), then goes live.
    * Ephemeral events (`progress`, `log`, `telemetry`) carry no `id`.
    * The stream ends with `event: end` after the run reaches a terminal status and the
      backlog is flushed.
    * Response headers: `Cache-Control: no-cache`, `X-Accel-Buffering: no`.

    Args:
        run_id (UUID):
        after_seq (int | Unset):
        include (list[StreamRunEventsIncludeItem] | Unset):
        last_event_id (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | RunStreamEvent]
    """

    kwargs = _get_kwargs(
        run_id=run_id,
        after_seq=after_seq,
        include=include,
        last_event_id=last_event_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    run_id: UUID,
    *,
    client: AuthenticatedClient,
    after_seq: int | Unset = UNSET,
    include: list[StreamRunEventsIncludeItem] | Unset = UNSET,
    last_event_id: str | Unset = UNSET,
) -> Problem | RunStreamEvent | None:
    """Live run stream (SSE). See RunStreamEvent for framing.

     Framing (one SSE message per event):
    ```
    id: 42            # only for persisted events (= run_events.seq)
    event: metrics    # RunStreamEvent.event
    data: {...}       # JSON, schema by event name (RunStreamEvent oneOf)
    ```
    * `retry: 3000` is sent first. `event: heartbeat` every 15 s (Cloudflare idles at ~100 s).
    * The caller's session / PAT and workspace membership are re-checked every 15 s; the stream
      ends (no `end` event) when either is gone, and after at most 15 min in any case - the
      client reconnects with `Last-Event-ID` (CR-BE-S1).
    * With `Last-Event-ID: <seq>` (or `?after_seq=`) the server first replays persisted events
      with seq > N (status, metrics, checkpoint, warning, error, model), then goes live.
    * Ephemeral events (`progress`, `log`, `telemetry`) carry no `id`.
    * The stream ends with `event: end` after the run reaches a terminal status and the
      backlog is flushed.
    * Response headers: `Cache-Control: no-cache`, `X-Accel-Buffering: no`.

    Args:
        run_id (UUID):
        after_seq (int | Unset):
        include (list[StreamRunEventsIncludeItem] | Unset):
        last_event_id (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | RunStreamEvent
    """

    return sync_detailed(
        run_id=run_id,
        client=client,
        after_seq=after_seq,
        include=include,
        last_event_id=last_event_id,
    ).parsed


async def asyncio_detailed(
    run_id: UUID,
    *,
    client: AuthenticatedClient,
    after_seq: int | Unset = UNSET,
    include: list[StreamRunEventsIncludeItem] | Unset = UNSET,
    last_event_id: str | Unset = UNSET,
) -> Response[Problem | RunStreamEvent]:
    """Live run stream (SSE). See RunStreamEvent for framing.

     Framing (one SSE message per event):
    ```
    id: 42            # only for persisted events (= run_events.seq)
    event: metrics    # RunStreamEvent.event
    data: {...}       # JSON, schema by event name (RunStreamEvent oneOf)
    ```
    * `retry: 3000` is sent first. `event: heartbeat` every 15 s (Cloudflare idles at ~100 s).
    * The caller's session / PAT and workspace membership are re-checked every 15 s; the stream
      ends (no `end` event) when either is gone, and after at most 15 min in any case - the
      client reconnects with `Last-Event-ID` (CR-BE-S1).
    * With `Last-Event-ID: <seq>` (or `?after_seq=`) the server first replays persisted events
      with seq > N (status, metrics, checkpoint, warning, error, model), then goes live.
    * Ephemeral events (`progress`, `log`, `telemetry`) carry no `id`.
    * The stream ends with `event: end` after the run reaches a terminal status and the
      backlog is flushed.
    * Response headers: `Cache-Control: no-cache`, `X-Accel-Buffering: no`.

    Args:
        run_id (UUID):
        after_seq (int | Unset):
        include (list[StreamRunEventsIncludeItem] | Unset):
        last_event_id (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | RunStreamEvent]
    """

    kwargs = _get_kwargs(
        run_id=run_id,
        after_seq=after_seq,
        include=include,
        last_event_id=last_event_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    run_id: UUID,
    *,
    client: AuthenticatedClient,
    after_seq: int | Unset = UNSET,
    include: list[StreamRunEventsIncludeItem] | Unset = UNSET,
    last_event_id: str | Unset = UNSET,
) -> Problem | RunStreamEvent | None:
    """Live run stream (SSE). See RunStreamEvent for framing.

     Framing (one SSE message per event):
    ```
    id: 42            # only for persisted events (= run_events.seq)
    event: metrics    # RunStreamEvent.event
    data: {...}       # JSON, schema by event name (RunStreamEvent oneOf)
    ```
    * `retry: 3000` is sent first. `event: heartbeat` every 15 s (Cloudflare idles at ~100 s).
    * The caller's session / PAT and workspace membership are re-checked every 15 s; the stream
      ends (no `end` event) when either is gone, and after at most 15 min in any case - the
      client reconnects with `Last-Event-ID` (CR-BE-S1).
    * With `Last-Event-ID: <seq>` (or `?after_seq=`) the server first replays persisted events
      with seq > N (status, metrics, checkpoint, warning, error, model), then goes live.
    * Ephemeral events (`progress`, `log`, `telemetry`) carry no `id`.
    * The stream ends with `event: end` after the run reaches a terminal status and the
      backlog is flushed.
    * Response headers: `Cache-Control: no-cache`, `X-Accel-Buffering: no`.

    Args:
        run_id (UUID):
        after_seq (int | Unset):
        include (list[StreamRunEventsIncludeItem] | Unset):
        last_event_id (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | RunStreamEvent
    """

    return (
        await asyncio_detailed(
            run_id=run_id,
            client=client,
            after_seq=after_seq,
            include=include,
            last_event_id=last_event_id,
        )
    ).parsed
