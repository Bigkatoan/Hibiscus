from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.problem import Problem
from ...models.run_comparison import RunComparison
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    ids: list[UUID],
    keys: list[str] | Unset = UNSET,
    max_points: int | Unset = 1000,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    json_ids = []
    for ids_item_data in ids:
        ids_item = str(ids_item_data)
        json_ids.append(ids_item)

    params["ids"] = json_ids

    json_keys: list[str] | Unset = UNSET
    if not isinstance(keys, Unset):
        json_keys = keys

    params["keys"] = json_keys

    params["max_points"] = max_points

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/runs/compare",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Problem | RunComparison | None:
    if response.status_code == 200:
        response_200 = RunComparison.from_dict(response.json())

        return response_200

    if response.status_code == 401:
        response_401 = Problem.from_dict(response.json())

        return response_401

    if response.status_code == 404:
        response_404 = Problem.from_dict(response.json())

        return response_404

    if response.status_code == 422:
        response_422 = Problem.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Problem | RunComparison]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    ids: list[UUID],
    keys: list[str] | Unset = UNSET,
    max_points: int | Unset = 1000,
) -> Response[Problem | RunComparison]:
    """Overlay metric series and diff configs of 2..8 runs (same workspace)

    Args:
        ids (list[UUID]):
        keys (list[str] | Unset):
        max_points (int | Unset):  Default: 1000.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | RunComparison]
    """

    kwargs = _get_kwargs(
        ids=ids,
        keys=keys,
        max_points=max_points,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    ids: list[UUID],
    keys: list[str] | Unset = UNSET,
    max_points: int | Unset = 1000,
) -> Problem | RunComparison | None:
    """Overlay metric series and diff configs of 2..8 runs (same workspace)

    Args:
        ids (list[UUID]):
        keys (list[str] | Unset):
        max_points (int | Unset):  Default: 1000.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | RunComparison
    """

    return sync_detailed(
        client=client,
        ids=ids,
        keys=keys,
        max_points=max_points,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    ids: list[UUID],
    keys: list[str] | Unset = UNSET,
    max_points: int | Unset = 1000,
) -> Response[Problem | RunComparison]:
    """Overlay metric series and diff configs of 2..8 runs (same workspace)

    Args:
        ids (list[UUID]):
        keys (list[str] | Unset):
        max_points (int | Unset):  Default: 1000.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | RunComparison]
    """

    kwargs = _get_kwargs(
        ids=ids,
        keys=keys,
        max_points=max_points,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    ids: list[UUID],
    keys: list[str] | Unset = UNSET,
    max_points: int | Unset = 1000,
) -> Problem | RunComparison | None:
    """Overlay metric series and diff configs of 2..8 runs (same workspace)

    Args:
        ids (list[UUID]):
        keys (list[str] | Unset):
        max_points (int | Unset):  Default: 1000.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | RunComparison
    """

    return (
        await asyncio_detailed(
            client=client,
            ids=ids,
            keys=keys,
            max_points=max_points,
        )
    ).parsed
