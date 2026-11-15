from http import HTTPStatus
from typing import Any, Optional, Union, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.problem import Problem
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_csrf_token, Unset):
        headers["X-CSRF-Token"] = x_csrf_token

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/auth/refresh",
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[Any, Problem]]:
    if response.status_code == 204:
        response_204 = cast(Any, None)
        return response_204

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
) -> Response[Union[Any, Problem]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> Response[Union[Any, Problem]]:
    """Rotate the refresh token and issue a new access token

     Reads `hb_refresh` (cookie, path `/api/v1/auth`). Requires `X-CSRF-Token`. Presenting an
    already-rotated refresh token revokes the whole session family (401
    `refresh_reuse_detected`), with two exceptions (CR-BE-S1): (a) its successor has never been
    used (no request carried an access token issued with it, e.g. the rotation response was
    aborted by a page reload) - the token is rotated again and new cookies are set; (b) within
    10 s of the rotation (concurrent tab) - 204 without cookies. The SPA calls this when any
    request returns 401 `token_expired`, then retries once.

    Args:
        x_csrf_token (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Any, Problem]]
    """

    kwargs = _get_kwargs(
        x_csrf_token=x_csrf_token,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> Optional[Union[Any, Problem]]:
    """Rotate the refresh token and issue a new access token

     Reads `hb_refresh` (cookie, path `/api/v1/auth`). Requires `X-CSRF-Token`. Presenting an
    already-rotated refresh token revokes the whole session family (401
    `refresh_reuse_detected`), with two exceptions (CR-BE-S1): (a) its successor has never been
    used (no request carried an access token issued with it, e.g. the rotation response was
    aborted by a page reload) - the token is rotated again and new cookies are set; (b) within
    10 s of the rotation (concurrent tab) - 204 without cookies. The SPA calls this when any
    request returns 401 `token_expired`, then retries once.

    Args:
        x_csrf_token (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Any, Problem]
    """

    return sync_detailed(
        client=client,
        x_csrf_token=x_csrf_token,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> Response[Union[Any, Problem]]:
    """Rotate the refresh token and issue a new access token

     Reads `hb_refresh` (cookie, path `/api/v1/auth`). Requires `X-CSRF-Token`. Presenting an
    already-rotated refresh token revokes the whole session family (401
    `refresh_reuse_detected`), with two exceptions (CR-BE-S1): (a) its successor has never been
    used (no request carried an access token issued with it, e.g. the rotation response was
    aborted by a page reload) - the token is rotated again and new cookies are set; (b) within
    10 s of the rotation (concurrent tab) - 204 without cookies. The SPA calls this when any
    request returns 401 `token_expired`, then retries once.

    Args:
        x_csrf_token (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Any, Problem]]
    """

    kwargs = _get_kwargs(
        x_csrf_token=x_csrf_token,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> Optional[Union[Any, Problem]]:
    """Rotate the refresh token and issue a new access token

     Reads `hb_refresh` (cookie, path `/api/v1/auth`). Requires `X-CSRF-Token`. Presenting an
    already-rotated refresh token revokes the whole session family (401
    `refresh_reuse_detected`), with two exceptions (CR-BE-S1): (a) its successor has never been
    used (no request carried an access token issued with it, e.g. the rotation response was
    aborted by a page reload) - the token is rotated again and new cookies are set; (b) within
    10 s of the rotation (concurrent tab) - 204 without cookies. The SPA calls this when any
    request returns 401 `token_expired`, then retries once.

    Args:
        x_csrf_token (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Any, Problem]
    """

    return (
        await asyncio_detailed(
            client=client,
            x_csrf_token=x_csrf_token,
        )
    ).parsed
