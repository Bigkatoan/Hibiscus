from http import HTTPStatus
from typing import Any, Optional, Union
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.dataset_preview import DatasetPreview
from ...models.problem import Problem
from ...types import Response


def _get_kwargs(
    version_id: UUID,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/dataset-versions/{version_id}/preview".format(
            version_id=version_id,
        ),
    }

    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[DatasetPreview, Problem]]:
    if response.status_code == 200:
        response_200 = DatasetPreview.from_dict(response.json())

        return response_200

    if response.status_code == 401:
        response_401 = Problem.from_dict(response.json())

        return response_401

    if response.status_code == 404:
        response_404 = Problem.from_dict(response.json())

        return response_404

    if response.status_code == 409:
        response_409 = Problem.from_dict(response.json())

        return response_409

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Response[Union[DatasetPreview, Problem]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    version_id: UUID,
    *,
    client: AuthenticatedClient,
) -> Response[Union[DatasetPreview, Problem]]:
    """Episode list, thumbnails, length distribution (available when status=ready or invalid)

    Args:
        version_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[DatasetPreview, Problem]]
    """

    kwargs = _get_kwargs(
        version_id=version_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    version_id: UUID,
    *,
    client: AuthenticatedClient,
) -> Optional[Union[DatasetPreview, Problem]]:
    """Episode list, thumbnails, length distribution (available when status=ready or invalid)

    Args:
        version_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[DatasetPreview, Problem]
    """

    return sync_detailed(
        version_id=version_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    version_id: UUID,
    *,
    client: AuthenticatedClient,
) -> Response[Union[DatasetPreview, Problem]]:
    """Episode list, thumbnails, length distribution (available when status=ready or invalid)

    Args:
        version_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[DatasetPreview, Problem]]
    """

    kwargs = _get_kwargs(
        version_id=version_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    version_id: UUID,
    *,
    client: AuthenticatedClient,
) -> Optional[Union[DatasetPreview, Problem]]:
    """Episode list, thumbnails, length distribution (available when status=ready or invalid)

    Args:
        version_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[DatasetPreview, Problem]
    """

    return (
        await asyncio_detailed(
            version_id=version_id,
            client=client,
        )
    ).parsed
