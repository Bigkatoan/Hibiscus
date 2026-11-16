from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.episode_detail import EpisodeDetail
from ...models.problem import Problem
from ...types import UNSET, Response, Unset


def _get_kwargs(
    version_id: UUID,
    episode_index: int,
    *,
    max_points: int | Unset = 1000,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    params["max_points"] = max_points

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/dataset-versions/{version_id}/episodes/{episode_index}".format(
            version_id=quote(str(version_id), safe=""),
            episode_index=quote(str(episode_index), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> EpisodeDetail | Problem | None:
    if response.status_code == 200:
        response_200 = EpisodeDetail.from_dict(response.json())

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
) -> Response[EpisodeDetail | Problem]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    version_id: UUID,
    episode_index: int,
    *,
    client: AuthenticatedClient,
    max_points: int | Unset = 1000,
) -> Response[EpisodeDetail | Problem]:
    """One episode - per-joint time series (downsampled) and video locations

    Args:
        version_id (UUID):
        episode_index (int):
        max_points (int | Unset):  Default: 1000.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[EpisodeDetail | Problem]
    """

    kwargs = _get_kwargs(
        version_id=version_id,
        episode_index=episode_index,
        max_points=max_points,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    version_id: UUID,
    episode_index: int,
    *,
    client: AuthenticatedClient,
    max_points: int | Unset = 1000,
) -> EpisodeDetail | Problem | None:
    """One episode - per-joint time series (downsampled) and video locations

    Args:
        version_id (UUID):
        episode_index (int):
        max_points (int | Unset):  Default: 1000.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        EpisodeDetail | Problem
    """

    return sync_detailed(
        version_id=version_id,
        episode_index=episode_index,
        client=client,
        max_points=max_points,
    ).parsed


async def asyncio_detailed(
    version_id: UUID,
    episode_index: int,
    *,
    client: AuthenticatedClient,
    max_points: int | Unset = 1000,
) -> Response[EpisodeDetail | Problem]:
    """One episode - per-joint time series (downsampled) and video locations

    Args:
        version_id (UUID):
        episode_index (int):
        max_points (int | Unset):  Default: 1000.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[EpisodeDetail | Problem]
    """

    kwargs = _get_kwargs(
        version_id=version_id,
        episode_index=episode_index,
        max_points=max_points,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    version_id: UUID,
    episode_index: int,
    *,
    client: AuthenticatedClient,
    max_points: int | Unset = 1000,
) -> EpisodeDetail | Problem | None:
    """One episode - per-joint time series (downsampled) and video locations

    Args:
        version_id (UUID):
        episode_index (int):
        max_points (int | Unset):  Default: 1000.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        EpisodeDetail | Problem
    """

    return (
        await asyncio_detailed(
            version_id=version_id,
            episode_index=episode_index,
            client=client,
            max_points=max_points,
        )
    ).parsed
