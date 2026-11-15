from http import HTTPStatus
from typing import Any, Optional, Union

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.problem import Problem
from ...models.secret_status import SecretStatus
from ...models.set_hf_token_body import SetHfTokenBody
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    body: SetHfTokenBody,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_csrf_token, Unset):
        headers["X-CSRF-Token"] = x_csrf_token

    _kwargs: dict[str, Any] = {
        "method": "put",
        "url": "/users/me/secrets/hf-token",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[Problem, SecretStatus]]:
    if response.status_code == 200:
        response_200 = SecretStatus.from_dict(response.json())

        return response_200

    if response.status_code == 401:
        response_401 = Problem.from_dict(response.json())

        return response_401

    if response.status_code == 422:
        response_422 = Problem.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Response[Union[Problem, SecretStatus]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: SetHfTokenBody,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> Response[Union[Problem, SecretStatus]]:
    """Store (encrypted) a Hugging Face token used for imports and Hub pushes

    Args:
        x_csrf_token (Union[Unset, str]):
        body (SetHfTokenBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Problem, SecretStatus]]
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
    body: SetHfTokenBody,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> Optional[Union[Problem, SecretStatus]]:
    """Store (encrypted) a Hugging Face token used for imports and Hub pushes

    Args:
        x_csrf_token (Union[Unset, str]):
        body (SetHfTokenBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Problem, SecretStatus]
    """

    return sync_detailed(
        client=client,
        body=body,
        x_csrf_token=x_csrf_token,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: SetHfTokenBody,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> Response[Union[Problem, SecretStatus]]:
    """Store (encrypted) a Hugging Face token used for imports and Hub pushes

    Args:
        x_csrf_token (Union[Unset, str]):
        body (SetHfTokenBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Problem, SecretStatus]]
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
    body: SetHfTokenBody,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> Optional[Union[Problem, SecretStatus]]:
    """Store (encrypted) a Hugging Face token used for imports and Hub pushes

    Args:
        x_csrf_token (Union[Unset, str]):
        body (SetHfTokenBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Problem, SecretStatus]
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
            x_csrf_token=x_csrf_token,
        )
    ).parsed
