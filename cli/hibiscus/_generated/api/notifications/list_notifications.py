from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.notification_page import NotificationPage
from ...models.problem import Problem
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    unread: bool | Unset = UNSET,
    limit: int | Unset = 50,
    cursor: str | Unset = UNSET,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    params["unread"] = unread

    params["limit"] = limit

    params["cursor"] = cursor

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/notifications",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> NotificationPage | Problem | None:
    if response.status_code == 200:
        response_200 = NotificationPage.from_dict(response.json())

        return response_200

    if response.status_code == 401:
        response_401 = Problem.from_dict(response.json())

        return response_401

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[NotificationPage | Problem]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    unread: bool | Unset = UNSET,
    limit: int | Unset = 50,
    cursor: str | Unset = UNSET,
) -> Response[NotificationPage | Problem]:
    """In-app notifications, newest first

    Args:
        unread (bool | Unset):
        limit (int | Unset):  Default: 50.
        cursor (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[NotificationPage | Problem]
    """

    kwargs = _get_kwargs(
        unread=unread,
        limit=limit,
        cursor=cursor,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    unread: bool | Unset = UNSET,
    limit: int | Unset = 50,
    cursor: str | Unset = UNSET,
) -> NotificationPage | Problem | None:
    """In-app notifications, newest first

    Args:
        unread (bool | Unset):
        limit (int | Unset):  Default: 50.
        cursor (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        NotificationPage | Problem
    """

    return sync_detailed(
        client=client,
        unread=unread,
        limit=limit,
        cursor=cursor,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    unread: bool | Unset = UNSET,
    limit: int | Unset = 50,
    cursor: str | Unset = UNSET,
) -> Response[NotificationPage | Problem]:
    """In-app notifications, newest first

    Args:
        unread (bool | Unset):
        limit (int | Unset):  Default: 50.
        cursor (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[NotificationPage | Problem]
    """

    kwargs = _get_kwargs(
        unread=unread,
        limit=limit,
        cursor=cursor,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    unread: bool | Unset = UNSET,
    limit: int | Unset = 50,
    cursor: str | Unset = UNSET,
) -> NotificationPage | Problem | None:
    """In-app notifications, newest first

    Args:
        unread (bool | Unset):
        limit (int | Unset):  Default: 50.
        cursor (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        NotificationPage | Problem
    """

    return (
        await asyncio_detailed(
            client=client,
            unread=unread,
            limit=limit,
            cursor=cursor,
        )
    ).parsed
