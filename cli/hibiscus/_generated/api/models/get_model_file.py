from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.problem import Problem
from ...types import UNSET, Response, Unset


def _get_kwargs(
    model_id: UUID,
    path: str,
    *,
    range_: str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(range_, Unset):
        headers["Range"] = range_

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/models/{model_id}/files/{path}".format(
            model_id=quote(str(model_id), safe=""),
            path=quote(str(path), safe=""),
        ),
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Problem | str | None:
    if response.status_code == 200:
        response_200 = cast(str, response.content)
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
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Problem | str]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    model_id: UUID,
    path: str,
    *,
    client: AuthenticatedClient,
    range_: str | Unset = UNSET,
) -> Response[Problem | str]:
    """Download one bundle file (Range supported)

    Args:
        model_id (UUID):
        path (str):
        range_ (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | str]
    """

    kwargs = _get_kwargs(
        model_id=model_id,
        path=path,
        range_=range_,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    model_id: UUID,
    path: str,
    *,
    client: AuthenticatedClient,
    range_: str | Unset = UNSET,
) -> Problem | str | None:
    """Download one bundle file (Range supported)

    Args:
        model_id (UUID):
        path (str):
        range_ (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | str
    """

    return sync_detailed(
        model_id=model_id,
        path=path,
        client=client,
        range_=range_,
    ).parsed


async def asyncio_detailed(
    model_id: UUID,
    path: str,
    *,
    client: AuthenticatedClient,
    range_: str | Unset = UNSET,
) -> Response[Problem | str]:
    """Download one bundle file (Range supported)

    Args:
        model_id (UUID):
        path (str):
        range_ (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | str]
    """

    kwargs = _get_kwargs(
        model_id=model_id,
        path=path,
        range_=range_,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    model_id: UUID,
    path: str,
    *,
    client: AuthenticatedClient,
    range_: str | Unset = UNSET,
) -> Problem | str | None:
    """Download one bundle file (Range supported)

    Args:
        model_id (UUID):
        path (str):
        range_ (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | str
    """

    return (
        await asyncio_detailed(
            model_id=model_id,
            path=path,
            client=client,
            range_=range_,
        )
    ).parsed
