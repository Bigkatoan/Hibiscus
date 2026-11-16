from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.get_queue_response_200 import GetQueueResponse200
from ...models.problem import Problem
from ...types import Response


def _get_kwargs() -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/queue",
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> GetQueueResponse200 | Problem | None:
    if response.status_code == 200:
        response_200 = GetQueueResponse200.from_dict(response.json())

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
) -> Response[GetQueueResponse200 | Problem]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
) -> Response[GetQueueResponse200 | Problem]:
    """Global queue in scheduling order (runs of other workspaces are anonymised)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GetQueueResponse200 | Problem]
    """

    kwargs = _get_kwargs()

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
) -> GetQueueResponse200 | Problem | None:
    """Global queue in scheduling order (runs of other workspaces are anonymised)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GetQueueResponse200 | Problem
    """

    return sync_detailed(
        client=client,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
) -> Response[GetQueueResponse200 | Problem]:
    """Global queue in scheduling order (runs of other workspaces are anonymised)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GetQueueResponse200 | Problem]
    """

    kwargs = _get_kwargs()

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
) -> GetQueueResponse200 | Problem | None:
    """Global queue in scheduling order (runs of other workspaces are anonymised)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GetQueueResponse200 | Problem
    """

    return (
        await asyncio_detailed(
            client=client,
        )
    ).parsed
