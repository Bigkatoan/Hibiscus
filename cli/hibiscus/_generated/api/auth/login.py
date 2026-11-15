from http import HTTPStatus
from typing import Any, Optional, Union

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.login_request import LoginRequest
from ...models.login_result import LoginResult
from ...models.problem import Problem
from ...types import Response


def _get_kwargs(
    *,
    body: LoginRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/auth/login",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[LoginResult, Problem]]:
    if response.status_code == 200:
        response_200 = LoginResult.from_dict(response.json())

        return response_200

    if response.status_code == 400:
        response_400 = Problem.from_dict(response.json())

        return response_400

    if response.status_code == 401:
        response_401 = Problem.from_dict(response.json())

        return response_401

    if response.status_code == 403:
        response_403 = Problem.from_dict(response.json())

        return response_403

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
    body: LoginRequest,
) -> Response[Union[LoginResult, Problem]]:
    """Password login (step 1)

     Returns `status=ok` (cookies set) or `status=mfa_required` with a 5-minute `mfa_token`
    to be completed via `POST /auth/login/2fa`. Users whose role requires 2FA but who have not
    enrolled get `status=ok` with `mfa_enrollment_required=true`: the session can only call
    `/auth/me`, `/auth/2fa/*`, `/auth/logout` until enrolment (others return 403
    `mfa_enrollment_required`). 5 consecutive failures lock the account with exponential
    backoff; while locked, login answers the same 401 `invalid_credentials` as for a wrong
    password or an unknown email, so a lock does not reveal that an account exists (CR-BE-S1;
    423 is no longer returned here). `turnstile_token` is required when the server reports
    `turnstile_required` (always in production).

    Args:
        body (LoginRequest):

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
    body: LoginRequest,
) -> Optional[Union[LoginResult, Problem]]:
    """Password login (step 1)

     Returns `status=ok` (cookies set) or `status=mfa_required` with a 5-minute `mfa_token`
    to be completed via `POST /auth/login/2fa`. Users whose role requires 2FA but who have not
    enrolled get `status=ok` with `mfa_enrollment_required=true`: the session can only call
    `/auth/me`, `/auth/2fa/*`, `/auth/logout` until enrolment (others return 403
    `mfa_enrollment_required`). 5 consecutive failures lock the account with exponential
    backoff; while locked, login answers the same 401 `invalid_credentials` as for a wrong
    password or an unknown email, so a lock does not reveal that an account exists (CR-BE-S1;
    423 is no longer returned here). `turnstile_token` is required when the server reports
    `turnstile_required` (always in production).

    Args:
        body (LoginRequest):

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
    body: LoginRequest,
) -> Response[Union[LoginResult, Problem]]:
    """Password login (step 1)

     Returns `status=ok` (cookies set) or `status=mfa_required` with a 5-minute `mfa_token`
    to be completed via `POST /auth/login/2fa`. Users whose role requires 2FA but who have not
    enrolled get `status=ok` with `mfa_enrollment_required=true`: the session can only call
    `/auth/me`, `/auth/2fa/*`, `/auth/logout` until enrolment (others return 403
    `mfa_enrollment_required`). 5 consecutive failures lock the account with exponential
    backoff; while locked, login answers the same 401 `invalid_credentials` as for a wrong
    password or an unknown email, so a lock does not reveal that an account exists (CR-BE-S1;
    423 is no longer returned here). `turnstile_token` is required when the server reports
    `turnstile_required` (always in production).

    Args:
        body (LoginRequest):

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
    body: LoginRequest,
) -> Optional[Union[LoginResult, Problem]]:
    """Password login (step 1)

     Returns `status=ok` (cookies set) or `status=mfa_required` with a 5-minute `mfa_token`
    to be completed via `POST /auth/login/2fa`. Users whose role requires 2FA but who have not
    enrolled get `status=ok` with `mfa_enrollment_required=true`: the session can only call
    `/auth/me`, `/auth/2fa/*`, `/auth/logout` until enrolment (others return 403
    `mfa_enrollment_required`). 5 consecutive failures lock the account with exponential
    backoff; while locked, login answers the same 401 `invalid_credentials` as for a wrong
    password or an unknown email, so a lock does not reveal that an account exists (CR-BE-S1;
    423 is no longer returned here). `turnstile_token` is required when the server reports
    `turnstile_required` (always in production).

    Args:
        body (LoginRequest):

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
