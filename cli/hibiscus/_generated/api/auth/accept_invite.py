from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.membership import Membership
from ...models.problem import Problem
from ...types import Response


def _get_kwargs(
    token: str,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/auth/invites/{token}/accept".format(
            token=quote(str(token), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Membership | Problem | None:
    if response.status_code == 200:
        response_200 = Membership.from_dict(response.json())

        return response_200

    if response.status_code == 401:
        response_401 = Problem.from_dict(response.json())

        return response_401

    if response.status_code == 403:
        response_403 = Problem.from_dict(response.json())

        return response_403

    if response.status_code == 404:
        response_404 = Problem.from_dict(response.json())

        return response_404

    if response.status_code == 409:
        response_409 = Problem.from_dict(response.json())

        return response_409

    if response.status_code == 410:
        response_410 = Problem.from_dict(response.json())

        return response_410

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Membership | Problem]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    token: str,
    *,
    client: AuthenticatedClient,
) -> Response[Membership | Problem]:
    """Accept an invite with the currently logged-in account

     Deprecated (CR-BE-S1) - use `POST /auth/invites/accept`; the token in the path is redacted from
    access logs.

    Args:
        token (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Membership | Problem]
    """

    kwargs = _get_kwargs(
        token=token,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    token: str,
    *,
    client: AuthenticatedClient,
) -> Membership | Problem | None:
    """Accept an invite with the currently logged-in account

     Deprecated (CR-BE-S1) - use `POST /auth/invites/accept`; the token in the path is redacted from
    access logs.

    Args:
        token (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Membership | Problem
    """

    return sync_detailed(
        token=token,
        client=client,
    ).parsed


async def asyncio_detailed(
    token: str,
    *,
    client: AuthenticatedClient,
) -> Response[Membership | Problem]:
    """Accept an invite with the currently logged-in account

     Deprecated (CR-BE-S1) - use `POST /auth/invites/accept`; the token in the path is redacted from
    access logs.

    Args:
        token (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Membership | Problem]
    """

    kwargs = _get_kwargs(
        token=token,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    token: str,
    *,
    client: AuthenticatedClient,
) -> Membership | Problem | None:
    """Accept an invite with the currently logged-in account

     Deprecated (CR-BE-S1) - use `POST /auth/invites/accept`; the token in the path is redacted from
    access logs.

    Args:
        token (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Membership | Problem
    """

    return (
        await asyncio_detailed(
            token=token,
            client=client,
        )
    ).parsed
