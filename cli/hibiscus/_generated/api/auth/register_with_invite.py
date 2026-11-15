from http import HTTPStatus
from typing import Any, Optional, Union

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.login_result import LoginResult
from ...models.problem import Problem
from ...models.register_invite_request import RegisterInviteRequest
from ...types import Response


def _get_kwargs(
    *,
    body: RegisterInviteRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/auth/register-invite",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[LoginResult, Problem]]:
    if response.status_code == 201:
        response_201 = LoginResult.from_dict(response.json())

        return response_201

    if response.status_code == 400:
        response_400 = Problem.from_dict(response.json())

        return response_400

    if response.status_code == 409:
        response_409 = Problem.from_dict(response.json())

        return response_409

    if response.status_code == 410:
        response_410 = Problem.from_dict(response.json())

        return response_410

    if response.status_code == 422:
        response_422 = Problem.from_dict(response.json())

        return response_422

    if response.status_code == 429:
        response_429 = Problem.from_dict(response.json())

        return response_429

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Response[Union[LoginResult, Problem]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: Union[AuthenticatedClient, Client],
    body: RegisterInviteRequest,
) -> Response[Union[LoginResult, Problem]]:
    """Create an account from an invite (email is pre-verified by the invite)

     Only path to create an account (no open sign-up). If the invite email already has an
    account, use `POST /auth/invites/accept` while logged in instead (409 `email_taken`).
    On success the session cookies are set exactly like a successful login.

    Args:
        body (RegisterInviteRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[LoginResult, Problem]]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: Union[AuthenticatedClient, Client],
    body: RegisterInviteRequest,
) -> Optional[Union[LoginResult, Problem]]:
    """Create an account from an invite (email is pre-verified by the invite)

     Only path to create an account (no open sign-up). If the invite email already has an
    account, use `POST /auth/invites/accept` while logged in instead (409 `email_taken`).
    On success the session cookies are set exactly like a successful login.

    Args:
        body (RegisterInviteRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[LoginResult, Problem]
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: Union[AuthenticatedClient, Client],
    body: RegisterInviteRequest,
) -> Response[Union[LoginResult, Problem]]:
    """Create an account from an invite (email is pre-verified by the invite)

     Only path to create an account (no open sign-up). If the invite email already has an
    account, use `POST /auth/invites/accept` while logged in instead (409 `email_taken`).
    On success the session cookies are set exactly like a successful login.

    Args:
        body (RegisterInviteRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[LoginResult, Problem]]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: Union[AuthenticatedClient, Client],
    body: RegisterInviteRequest,
) -> Optional[Union[LoginResult, Problem]]:
    """Create an account from an invite (email is pre-verified by the invite)

     Only path to create an account (no open sign-up). If the invite email already has an
    account, use `POST /auth/invites/accept` while logged in instead (409 `email_taken`).
    On success the session cookies are set exactly like a successful login.

    Args:
        body (RegisterInviteRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[LoginResult, Problem]
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
