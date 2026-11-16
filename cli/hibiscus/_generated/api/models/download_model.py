from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.problem import Problem
from ...types import UNSET, Response, Unset


def _get_kwargs(
    model_id: UUID,
    *,
    range_: str | Unset = UNSET,
    if_range: str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(range_, Unset):
        headers["Range"] = range_

    if not isinstance(if_range, Unset):
        headers["If-Range"] = if_range

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/models/{model_id}/download".format(
            model_id=quote(str(model_id), safe=""),
        ),
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Problem | None:
    if response.status_code == 401:
        response_401 = Problem.from_dict(response.json())

        return response_401

    if response.status_code == 404:
        response_404 = Problem.from_dict(response.json())

        return response_404

    if response.status_code == 409:
        response_409 = Problem.from_dict(response.json())

        return response_409

    if response.status_code == 416:
        response_416 = Problem.from_dict(response.json())

        return response_416

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Problem]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    model_id: UUID,
    *,
    client: AuthenticatedClient,
    range_: str | Unset = UNSET,
    if_range: str | Unset = UNSET,
) -> Response[Problem]:
    """Download the bundle zip (Range supported for resume; ETag = bundle sha256)

     Audited (`model.download`). 409 `model_not_ready` unless status=ready.

    Args:
        model_id (UUID):
        range_ (str | Unset):
        if_range (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem]
    """

    kwargs = _get_kwargs(
        model_id=model_id,
        range_=range_,
        if_range=if_range,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    model_id: UUID,
    *,
    client: AuthenticatedClient,
    range_: str | Unset = UNSET,
    if_range: str | Unset = UNSET,
) -> Problem | None:
    """Download the bundle zip (Range supported for resume; ETag = bundle sha256)

     Audited (`model.download`). 409 `model_not_ready` unless status=ready.

    Args:
        model_id (UUID):
        range_ (str | Unset):
        if_range (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem
    """

    return sync_detailed(
        model_id=model_id,
        client=client,
        range_=range_,
        if_range=if_range,
    ).parsed


async def asyncio_detailed(
    model_id: UUID,
    *,
    client: AuthenticatedClient,
    range_: str | Unset = UNSET,
    if_range: str | Unset = UNSET,
) -> Response[Problem]:
    """Download the bundle zip (Range supported for resume; ETag = bundle sha256)

     Audited (`model.download`). 409 `model_not_ready` unless status=ready.

    Args:
        model_id (UUID):
        range_ (str | Unset):
        if_range (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem]
    """

    kwargs = _get_kwargs(
        model_id=model_id,
        range_=range_,
        if_range=if_range,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    model_id: UUID,
    *,
    client: AuthenticatedClient,
    range_: str | Unset = UNSET,
    if_range: str | Unset = UNSET,
) -> Problem | None:
    """Download the bundle zip (Range supported for resume; ETag = bundle sha256)

     Audited (`model.download`). 409 `model_not_ready` unless status=ready.

    Args:
        model_id (UUID):
        range_ (str | Unset):
        if_range (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem
    """

    return (
        await asyncio_detailed(
            model_id=model_id,
            client=client,
            range_=range_,
            if_range=if_range,
        )
    ).parsed
