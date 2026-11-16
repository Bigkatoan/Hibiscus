import datetime
from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.get_run_telemetry_response_200 import GetRunTelemetryResponse200
from ...models.problem import Problem
from ...types import UNSET, Response, Unset


def _get_kwargs(
    run_id: UUID,
    *,
    since: datetime.datetime | Unset = UNSET,
    max_points: int | Unset = 2000,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    json_since: str | Unset = UNSET
    if not isinstance(since, Unset):
        json_since = since.isoformat()
    params["since"] = json_since

    params["max_points"] = max_points

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/runs/{run_id}/telemetry".format(
            run_id=quote(str(run_id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> GetRunTelemetryResponse200 | Problem | None:
    if response.status_code == 200:
        response_200 = GetRunTelemetryResponse200.from_dict(response.json())

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
) -> Response[GetRunTelemetryResponse200 | Problem]:
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
    since: datetime.datetime | Unset = UNSET,
    max_points: int | Unset = 2000,
) -> Response[GetRunTelemetryResponse200 | Problem]:
    """GPU telemetry samples recorded while this run held a GPU

    Args:
        run_id (UUID):
        since (datetime.datetime | Unset):
        max_points (int | Unset):  Default: 2000.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GetRunTelemetryResponse200 | Problem]
    """

    kwargs = _get_kwargs(
        run_id=run_id,
        since=since,
        max_points=max_points,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    run_id: UUID,
    *,
    client: AuthenticatedClient,
    since: datetime.datetime | Unset = UNSET,
    max_points: int | Unset = 2000,
) -> GetRunTelemetryResponse200 | Problem | None:
    """GPU telemetry samples recorded while this run held a GPU

    Args:
        run_id (UUID):
        since (datetime.datetime | Unset):
        max_points (int | Unset):  Default: 2000.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GetRunTelemetryResponse200 | Problem
    """

    return sync_detailed(
        run_id=run_id,
        client=client,
        since=since,
        max_points=max_points,
    ).parsed


async def asyncio_detailed(
    run_id: UUID,
    *,
    client: AuthenticatedClient,
    since: datetime.datetime | Unset = UNSET,
    max_points: int | Unset = 2000,
) -> Response[GetRunTelemetryResponse200 | Problem]:
    """GPU telemetry samples recorded while this run held a GPU

    Args:
        run_id (UUID):
        since (datetime.datetime | Unset):
        max_points (int | Unset):  Default: 2000.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GetRunTelemetryResponse200 | Problem]
    """

    kwargs = _get_kwargs(
        run_id=run_id,
        since=since,
        max_points=max_points,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    run_id: UUID,
    *,
    client: AuthenticatedClient,
    since: datetime.datetime | Unset = UNSET,
    max_points: int | Unset = 2000,
) -> GetRunTelemetryResponse200 | Problem | None:
    """GPU telemetry samples recorded while this run held a GPU

    Args:
        run_id (UUID):
        since (datetime.datetime | Unset):
        max_points (int | Unset):  Default: 2000.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GetRunTelemetryResponse200 | Problem
    """

    return (
        await asyncio_detailed(
            run_id=run_id,
            client=client,
            since=since,
            max_points=max_points,
        )
    ).parsed
