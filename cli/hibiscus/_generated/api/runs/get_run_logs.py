from http import HTTPStatus
from typing import Any, Optional, Union
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.problem import Problem
from ...types import UNSET, Response, Unset


def _get_kwargs(
    run_id: UUID,
    *,
    download: Union[Unset, bool] = False,
    range_: Union[Unset, str] = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(range_, Unset):
        headers["Range"] = range_

    params: dict[str, Any] = {}

    params["download"] = download

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/runs/{run_id}/logs".format(
            run_id=run_id,
        ),
        "params": params,
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[Problem, str]]:
    if response.status_code == 200:
        response_200 = response.text
        return response_200

    if response.status_code == 206:
        response_206 = response.text
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
) -> Response[Union[Problem, str]]:
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
    download: Union[Unset, bool] = False,
    range_: Union[Unset, str] = UNSET,
) -> Response[Union[Problem, str]]:
    r"""Raw log (all attempts concatenated, tqdm `\r` frames collapsed to the last frame)

     Byte-addressed: supports `Range: bytes=<from>-` for tailing; `?download=true` adds
    `Content-Disposition: attachment; filename=run-<number>.log`. Live tail via SSE `log` events.

    Args:
        run_id (UUID):
        download (Union[Unset, bool]):  Default: False.
        range_ (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Problem, str]]
    """

    kwargs = _get_kwargs(
        run_id=run_id,
        download=download,
        range_=range_,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    run_id: UUID,
    *,
    client: AuthenticatedClient,
    download: Union[Unset, bool] = False,
    range_: Union[Unset, str] = UNSET,
) -> Optional[Union[Problem, str]]:
    r"""Raw log (all attempts concatenated, tqdm `\r` frames collapsed to the last frame)

     Byte-addressed: supports `Range: bytes=<from>-` for tailing; `?download=true` adds
    `Content-Disposition: attachment; filename=run-<number>.log`. Live tail via SSE `log` events.

    Args:
        run_id (UUID):
        download (Union[Unset, bool]):  Default: False.
        range_ (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Problem, str]
    """

    return sync_detailed(
        run_id=run_id,
        client=client,
        download=download,
        range_=range_,
    ).parsed


async def asyncio_detailed(
    run_id: UUID,
    *,
    client: AuthenticatedClient,
    download: Union[Unset, bool] = False,
    range_: Union[Unset, str] = UNSET,
) -> Response[Union[Problem, str]]:
    r"""Raw log (all attempts concatenated, tqdm `\r` frames collapsed to the last frame)

     Byte-addressed: supports `Range: bytes=<from>-` for tailing; `?download=true` adds
    `Content-Disposition: attachment; filename=run-<number>.log`. Live tail via SSE `log` events.

    Args:
        run_id (UUID):
        download (Union[Unset, bool]):  Default: False.
        range_ (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Problem, str]]
    """

    kwargs = _get_kwargs(
        run_id=run_id,
        download=download,
        range_=range_,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    run_id: UUID,
    *,
    client: AuthenticatedClient,
    download: Union[Unset, bool] = False,
    range_: Union[Unset, str] = UNSET,
) -> Optional[Union[Problem, str]]:
    r"""Raw log (all attempts concatenated, tqdm `\r` frames collapsed to the last frame)

     Byte-addressed: supports `Range: bytes=<from>-` for tailing; `?download=true` adds
    `Content-Disposition: attachment; filename=run-<number>.log`. Live tail via SSE `log` events.

    Args:
        run_id (UUID):
        download (Union[Unset, bool]):  Default: False.
        range_ (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Problem, str]
    """

    return (
        await asyncio_detailed(
            run_id=run_id,
            client=client,
            download=download,
            range_=range_,
        )
    ).parsed
