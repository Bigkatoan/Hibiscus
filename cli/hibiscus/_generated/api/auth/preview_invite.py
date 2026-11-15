from http import HTTPStatus
from typing import Any, Optional, Union

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.invite_preview import InvitePreview
from ...models.problem import Problem
from ...models.token_request import TokenRequest
from ...types import Response


def _get_kwargs(
    *,
    body: TokenRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/auth/invites/preview",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[InvitePreview, Problem]]:
    if response.status_code == 200:
        response_200 = InvitePreview.from_dict(response.json())

        return response_200

    if response.status_code == 404:
        response_404 = Problem.from_dict(response.json())

        return response_404

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
) -> Response[Union[InvitePreview, Problem]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: Union[AuthenticatedClient, Client],
    body: TokenRequest,
) -> Response[Union[InvitePreview, Problem]]:
    """Inspect an invite link before registering / accepting (token in the body)

     The invite token is sent in the body so it never appears in a URL path (access logs,
    CR-BE-S1). Same answer as the deprecated `GET /auth/invites/{token}`.

    Args:
        body (TokenRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[InvitePreview, Problem]]
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
    body: TokenRequest,
) -> Optional[Union[InvitePreview, Problem]]:
    """Inspect an invite link before registering / accepting (token in the body)

     The invite token is sent in the body so it never appears in a URL path (access logs,
    CR-BE-S1). Same answer as the deprecated `GET /auth/invites/{token}`.

    Args:
        body (TokenRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[InvitePreview, Problem]
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: Union[AuthenticatedClient, Client],
    body: TokenRequest,
) -> Response[Union[InvitePreview, Problem]]:
    """Inspect an invite link before registering / accepting (token in the body)

     The invite token is sent in the body so it never appears in a URL path (access logs,
    CR-BE-S1). Same answer as the deprecated `GET /auth/invites/{token}`.

    Args:
        body (TokenRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[InvitePreview, Problem]]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: Union[AuthenticatedClient, Client],
    body: TokenRequest,
) -> Optional[Union[InvitePreview, Problem]]:
    """Inspect an invite link before registering / accepting (token in the body)

     The invite token is sent in the body so it never appears in a URL path (access logs,
    CR-BE-S1). Same answer as the deprecated `GET /auth/invites/{token}`.

    Args:
        body (TokenRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[InvitePreview, Problem]
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
