from http import HTTPStatus
from typing import Any, Optional, Union, cast
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.problem import Problem
from ...types import UNSET, Response, Unset


def _get_kwargs(
    version_id: UUID,
    path: str,
    *,
    range_: Union[Unset, str] = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(range_, Unset):
        headers["Range"] = range_

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/dataset-versions/{version_id}/media/{path}".format(
            version_id=version_id,
            path=path,
        ),
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[Any, Problem, str]]:
    if response.status_code == 200:
        response_200 = response.json()
        return response_200

    if response.status_code == 206:
        response_206 = cast(str, response.content)
        return response_206

    if response.status_code == 401:
        response_401 = Problem.from_dict(response.json())

        return response_401

    if response.status_code == 404:
        response_404 = Problem.from_dict(response.json())

        return response_404

    if response.status_code == 416:
        response_416 = Problem.from_dict(response.json())

        return response_416

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Response[Union[Any, Problem, str]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    version_id: UUID,
    path: str,
    *,
    client: AuthenticatedClient,
    range_: Union[Unset, str] = UNSET,
) -> Response[Union[Any, Problem, str]]:
    """Stream a media/meta file (HTTP Range supported, immutable caching)

    Args:
        version_id (UUID):
        path (str):
        range_ (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Any, Problem, str]]
    """

    kwargs = _get_kwargs(
        version_id=version_id,
        path=path,
        range_=range_,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    version_id: UUID,
    path: str,
    *,
    client: AuthenticatedClient,
    range_: Union[Unset, str] = UNSET,
) -> Optional[Union[Any, Problem, str]]:
    """Stream a media/meta file (HTTP Range supported, immutable caching)

    Args:
        version_id (UUID):
        path (str):
        range_ (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Any, Problem, str]
    """

    return sync_detailed(
        version_id=version_id,
        path=path,
        client=client,
        range_=range_,
    ).parsed


async def asyncio_detailed(
    version_id: UUID,
    path: str,
    *,
    client: AuthenticatedClient,
    range_: Union[Unset, str] = UNSET,
) -> Response[Union[Any, Problem, str]]:
    """Stream a media/meta file (HTTP Range supported, immutable caching)

    Args:
        version_id (UUID):
        path (str):
        range_ (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Any, Problem, str]]
    """

    kwargs = _get_kwargs(
        version_id=version_id,
        path=path,
        range_=range_,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    version_id: UUID,
    path: str,
    *,
    client: AuthenticatedClient,
    range_: Union[Unset, str] = UNSET,
) -> Optional[Union[Any, Problem, str]]:
    """Stream a media/meta file (HTTP Range supported, immutable caching)

    Args:
        version_id (UUID):
        path (str):
        range_ (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Any, Problem, str]
    """

    return (
        await asyncio_detailed(
            version_id=version_id,
            path=path,
            client=client,
            range_=range_,
        )
    ).parsed
