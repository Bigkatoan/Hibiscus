from http import HTTPStatus
from typing import Any, Optional, Union

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.problem import Problem
from ...models.recovery_codes import RecoveryCodes
from ...models.totp_code_request import TotpCodeRequest
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    body: TotpCodeRequest,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_csrf_token, Unset):
        headers["X-CSRF-Token"] = x_csrf_token

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/auth/2fa/recovery-codes",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[Problem, RecoveryCodes]]:
    if response.status_code == 200:
        response_200 = RecoveryCodes.from_dict(response.json())

        return response_200

    if response.status_code == 401:
        response_401 = Problem.from_dict(response.json())

        return response_401

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
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Response[Union[Problem, RecoveryCodes]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: TotpCodeRequest,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> Response[Union[Problem, RecoveryCodes]]:
    """Replace all recovery codes (old ones become invalid)

     Password / TOTP checks by a logged-in session are rate limited per user (10 per 15 min, 429)
    and count towards the account lockout like failed logins (423 `account_locked` while
    locked; CR-BE-S1).

    Args:
        x_csrf_token (Union[Unset, str]):
        body (TotpCodeRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Problem, RecoveryCodes]]
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
    body: TotpCodeRequest,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> Optional[Union[Problem, RecoveryCodes]]:
    """Replace all recovery codes (old ones become invalid)

     Password / TOTP checks by a logged-in session are rate limited per user (10 per 15 min, 429)
    and count towards the account lockout like failed logins (423 `account_locked` while
    locked; CR-BE-S1).

    Args:
        x_csrf_token (Union[Unset, str]):
        body (TotpCodeRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Problem, RecoveryCodes]
    """

    return sync_detailed(
        client=client,
        body=body,
        x_csrf_token=x_csrf_token,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: TotpCodeRequest,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> Response[Union[Problem, RecoveryCodes]]:
    """Replace all recovery codes (old ones become invalid)

     Password / TOTP checks by a logged-in session are rate limited per user (10 per 15 min, 429)
    and count towards the account lockout like failed logins (423 `account_locked` while
    locked; CR-BE-S1).

    Args:
        x_csrf_token (Union[Unset, str]):
        body (TotpCodeRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Problem, RecoveryCodes]]
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
    body: TotpCodeRequest,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> Optional[Union[Problem, RecoveryCodes]]:
    """Replace all recovery codes (old ones become invalid)

     Password / TOTP checks by a logged-in session are rate limited per user (10 per 15 min, 429)
    and count towards the account lockout like failed logins (423 `account_locked` while
    locked; CR-BE-S1).

    Args:
        x_csrf_token (Union[Unset, str]):
        body (TotpCodeRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Problem, RecoveryCodes]
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
            x_csrf_token=x_csrf_token,
        )
    ).parsed
