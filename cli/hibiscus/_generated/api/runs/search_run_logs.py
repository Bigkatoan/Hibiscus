from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.log_search_page import LogSearchPage
from ...models.problem import Problem
from ...models.search_run_logs_level import SearchRunLogsLevel
from ...types import UNSET, Response, Unset


def _get_kwargs(
    run_id: UUID,
    *,
    q: str,
    level: SearchRunLogsLevel | Unset = UNSET,
    limit: int | Unset = 50,
    cursor: str | Unset = UNSET,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    params["q"] = q

    json_level: str | Unset = UNSET
    if not isinstance(level, Unset):
        json_level = level.value

    params["level"] = json_level

    params["limit"] = limit

    params["cursor"] = cursor

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/runs/{run_id}/logs/search".format(
            run_id=quote(str(run_id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> LogSearchPage | Problem | None:
    if response.status_code == 200:
        response_200 = LogSearchPage.from_dict(response.json())

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
) -> Response[LogSearchPage | Problem]:
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
    q: str,
    level: SearchRunLogsLevel | Unset = UNSET,
    limit: int | Unset = 50,
    cursor: str | Unset = UNSET,
) -> Response[LogSearchPage | Problem]:
    """Case-insensitive substring search over log lines

    Args:
        run_id (UUID):
        q (str):
        level (SearchRunLogsLevel | Unset):
        limit (int | Unset):  Default: 50.
        cursor (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[LogSearchPage | Problem]
    """

    kwargs = _get_kwargs(
        run_id=run_id,
        q=q,
        level=level,
        limit=limit,
        cursor=cursor,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    run_id: UUID,
    *,
    client: AuthenticatedClient,
    q: str,
    level: SearchRunLogsLevel | Unset = UNSET,
    limit: int | Unset = 50,
    cursor: str | Unset = UNSET,
) -> LogSearchPage | Problem | None:
    """Case-insensitive substring search over log lines

    Args:
        run_id (UUID):
        q (str):
        level (SearchRunLogsLevel | Unset):
        limit (int | Unset):  Default: 50.
        cursor (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        LogSearchPage | Problem
    """

    return sync_detailed(
        run_id=run_id,
        client=client,
        q=q,
        level=level,
        limit=limit,
        cursor=cursor,
    ).parsed


async def asyncio_detailed(
    run_id: UUID,
    *,
    client: AuthenticatedClient,
    q: str,
    level: SearchRunLogsLevel | Unset = UNSET,
    limit: int | Unset = 50,
    cursor: str | Unset = UNSET,
) -> Response[LogSearchPage | Problem]:
    """Case-insensitive substring search over log lines

    Args:
        run_id (UUID):
        q (str):
        level (SearchRunLogsLevel | Unset):
        limit (int | Unset):  Default: 50.
        cursor (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[LogSearchPage | Problem]
    """

    kwargs = _get_kwargs(
        run_id=run_id,
        q=q,
        level=level,
        limit=limit,
        cursor=cursor,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    run_id: UUID,
    *,
    client: AuthenticatedClient,
    q: str,
    level: SearchRunLogsLevel | Unset = UNSET,
    limit: int | Unset = 50,
    cursor: str | Unset = UNSET,
) -> LogSearchPage | Problem | None:
    """Case-insensitive substring search over log lines

    Args:
        run_id (UUID):
        q (str):
        level (SearchRunLogsLevel | Unset):
        limit (int | Unset):  Default: 50.
        cursor (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        LogSearchPage | Problem
    """

    return (
        await asyncio_detailed(
            run_id=run_id,
            client=client,
            q=q,
            level=level,
            limit=limit,
            cursor=cursor,
        )
    ).parsed
