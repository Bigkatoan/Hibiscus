from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.model import Model
from ...models.problem import Problem
from ...types import Response


def _get_kwargs(
    model_id: UUID,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/models/{model_id}".format(
            model_id=quote(str(model_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Model | Problem | None:
    if response.status_code == 200:
        response_200 = Model.from_dict(response.json())

        return response_200

    if response.status_code == 401:
        response_401 = Problem.from_dict(response.json())

        return response_401

    if response.status_code == 404:
        response_404 = Problem.from_dict(response.json())

        return response_404

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Model | Problem]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    model_id: UUID,
    *,
    client: AuthenticatedClient,
) -> Response[Model | Problem]:
    """Model detail incl. verification and ONNX status

    Args:
        model_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Model | Problem]
    """

    kwargs = _get_kwargs(
        model_id=model_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    model_id: UUID,
    *,
    client: AuthenticatedClient,
) -> Model | Problem | None:
    """Model detail incl. verification and ONNX status

    Args:
        model_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Model | Problem
    """

    return sync_detailed(
        model_id=model_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    model_id: UUID,
    *,
    client: AuthenticatedClient,
) -> Response[Model | Problem]:
    """Model detail incl. verification and ONNX status

    Args:
        model_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Model | Problem]
    """

    kwargs = _get_kwargs(
        model_id=model_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    model_id: UUID,
    *,
    client: AuthenticatedClient,
) -> Model | Problem | None:
    """Model detail incl. verification and ONNX status

    Args:
        model_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Model | Problem
    """

    return (
        await asyncio_detailed(
            model_id=model_id,
            client=client,
        )
    ).parsed
