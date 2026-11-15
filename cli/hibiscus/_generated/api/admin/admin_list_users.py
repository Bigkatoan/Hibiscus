from http import HTTPStatus
from typing import Any, Optional, Union

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.admin_user_page import AdminUserPage
from ...models.problem import Problem
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    q: Union[Unset, str] = UNSET,
    limit: Union[Unset, int] = 50,
    cursor: Union[Unset, str] = UNSET,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    params["q"] = q

    params["limit"] = limit

    params["cursor"] = cursor

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/admin/users",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[AdminUserPage, Problem]]:
    if response.status_code == 200:
        response_200 = AdminUserPage.from_dict(response.json())

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
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Response[Union[AdminUserPage, Problem]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: Union[AuthenticatedClient, Client],
    q: Union[Unset, str] = UNSET,
    limit: Union[Unset, int] = 50,
    cursor: Union[Unset, str] = UNSET,
) -> Response[Union[AdminUserPage, Problem]]:
    """All users, by email

    Args:
        q (Union[Unset, str]):
        limit (Union[Unset, int]):  Default: 50.
        cursor (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[AdminUserPage, Problem]]
    """

    kwargs = _get_kwargs(
        q=q,
        limit=limit,
        cursor=cursor,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: Union[AuthenticatedClient, Client],
    q: Union[Unset, str] = UNSET,
    limit: Union[Unset, int] = 50,
    cursor: Union[Unset, str] = UNSET,
) -> Optional[Union[AdminUserPage, Problem]]:
    """All users, by email

    Args:
        q (Union[Unset, str]):
        limit (Union[Unset, int]):  Default: 50.
        cursor (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[AdminUserPage, Problem]
    """

    return sync_detailed(
        client=client,
        q=q,
        limit=limit,
        cursor=cursor,
    ).parsed


async def asyncio_detailed(
    *,
    client: Union[AuthenticatedClient, Client],
    q: Union[Unset, str] = UNSET,
    limit: Union[Unset, int] = 50,
    cursor: Union[Unset, str] = UNSET,
) -> Response[Union[AdminUserPage, Problem]]:
    """All users, by email

    Args:
        q (Union[Unset, str]):
        limit (Union[Unset, int]):  Default: 50.
        cursor (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[AdminUserPage, Problem]]
    """

    kwargs = _get_kwargs(
        q=q,
        limit=limit,
        cursor=cursor,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: Union[AuthenticatedClient, Client],
    q: Union[Unset, str] = UNSET,
    limit: Union[Unset, int] = 50,
    cursor: Union[Unset, str] = UNSET,
) -> Optional[Union[AdminUserPage, Problem]]:
    """All users, by email

    Args:
        q (Union[Unset, str]):
        limit (Union[Unset, int]):  Default: 50.
        cursor (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[AdminUserPage, Problem]
    """

    return (
        await asyncio_detailed(
            client=client,
            q=q,
            limit=limit,
            cursor=cursor,
        )
    ).parsed
