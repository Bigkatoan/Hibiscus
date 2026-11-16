from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.change_password_request import ChangePasswordRequest
from ...models.problem import Problem
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    body: ChangePasswordRequest,
    x_csrf_token: str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_csrf_token, Unset):
        headers["X-CSRF-Token"] = x_csrf_token

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/auth/password/change",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | Problem | None:
    if response.status_code == 204:
        response_204 = cast(Any, None)
        return response_204

    if response.status_code == 401:
        response_401 = Problem.from_dict(response.json())

        return response_401

    if response.status_code == 422:
        response_422 = Problem.from_dict(response.json())

        return response_422

    if response.status_code == 423:
        response_423 = Problem.from_dict(response.json())

        return response_423

    if response.status_code == 429:
        response_429 = Problem.from_dict(response.json())

        return response_429

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Any | Problem]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: ChangePasswordRequest,
    x_csrf_token: str | Unset = UNSET,
) -> Response[Any | Problem]:
    """Change password (revokes all other sessions)

     Password / TOTP checks by a logged-in session are rate limited per user (10 per 15 min, 429)
    and count towards the account lockout like failed logins (423 `account_locked` while
    locked; CR-BE-S1).

    Args:
        x_csrf_token (str | Unset):
        body (ChangePasswordRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | Problem]
    """

    kwargs = _get_kwargs(
        body=body,
        x_csrf_token=x_csrf_token,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    body: ChangePasswordRequest,
    x_csrf_token: str | Unset = UNSET,
) -> Any | Problem | None:
    """Change password (revokes all other sessions)

     Password / TOTP checks by a logged-in session are rate limited per user (10 per 15 min, 429)
    and count towards the account lockout like failed logins (423 `account_locked` while
    locked; CR-BE-S1).

    Args:
        x_csrf_token (str | Unset):
        body (ChangePasswordRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | Problem
    """

    return sync_detailed(
        client=client,
        body=body,
        x_csrf_token=x_csrf_token,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: ChangePasswordRequest,
    x_csrf_token: str | Unset = UNSET,
) -> Response[Any | Problem]:
    """Change password (revokes all other sessions)

     Password / TOTP checks by a logged-in session are rate limited per user (10 per 15 min, 429)
    and count towards the account lockout like failed logins (423 `account_locked` while
    locked; CR-BE-S1).

    Args:
        x_csrf_token (str | Unset):
        body (ChangePasswordRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | Problem]
    """

    kwargs = _get_kwargs(
        body=body,
        x_csrf_token=x_csrf_token,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: ChangePasswordRequest,
    x_csrf_token: str | Unset = UNSET,
) -> Any | Problem | None:
    """Change password (revokes all other sessions)

     Password / TOTP checks by a logged-in session are rate limited per user (10 per 15 min, 429)
    and count towards the account lockout like failed logins (423 `account_locked` while
    locked; CR-BE-S1).

    Args:
        x_csrf_token (str | Unset):
        body (ChangePasswordRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | Problem
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
            x_csrf_token=x_csrf_token,
        )
    ).parsed
