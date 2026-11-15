from http import HTTPStatus
from typing import Any, Optional, Union
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.dataset_version_page import DatasetVersionPage
from ...models.problem import Problem
from ...types import UNSET, Response, Unset


def _get_kwargs(
    dataset_id: UUID,
    *,
    limit: Union[Unset, int] = 50,
    cursor: Union[Unset, str] = UNSET,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    params["limit"] = limit

    params["cursor"] = cursor

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/datasets/{dataset_id}/versions".format(
            dataset_id=dataset_id,
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[DatasetVersionPage, Problem]]:
    if response.status_code == 200:
        response_200 = DatasetVersionPage.from_dict(response.json())

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
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Response[Union[DatasetVersionPage, Problem]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    dataset_id: UUID,
    *,
    client: AuthenticatedClient,
    limit: Union[Unset, int] = 50,
    cursor: Union[Unset, str] = UNSET,
) -> Response[Union[DatasetVersionPage, Problem]]:
    """Versions, highest version number first

    Args:
        dataset_id (UUID):
        limit (Union[Unset, int]):  Default: 50.
        cursor (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[DatasetVersionPage, Problem]]
    """

    kwargs = _get_kwargs(
        dataset_id=dataset_id,
        limit=limit,
        cursor=cursor,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    dataset_id: UUID,
    *,
    client: AuthenticatedClient,
    limit: Union[Unset, int] = 50,
    cursor: Union[Unset, str] = UNSET,
) -> Optional[Union[DatasetVersionPage, Problem]]:
    """Versions, highest version number first

    Args:
        dataset_id (UUID):
        limit (Union[Unset, int]):  Default: 50.
        cursor (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[DatasetVersionPage, Problem]
    """

    return sync_detailed(
        dataset_id=dataset_id,
        client=client,
        limit=limit,
        cursor=cursor,
    ).parsed


async def asyncio_detailed(
    dataset_id: UUID,
    *,
    client: AuthenticatedClient,
    limit: Union[Unset, int] = 50,
    cursor: Union[Unset, str] = UNSET,
) -> Response[Union[DatasetVersionPage, Problem]]:
    """Versions, highest version number first

    Args:
        dataset_id (UUID):
        limit (Union[Unset, int]):  Default: 50.
        cursor (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[DatasetVersionPage, Problem]]
    """

    kwargs = _get_kwargs(
        dataset_id=dataset_id,
        limit=limit,
        cursor=cursor,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    dataset_id: UUID,
    *,
    client: AuthenticatedClient,
    limit: Union[Unset, int] = 50,
    cursor: Union[Unset, str] = UNSET,
) -> Optional[Union[DatasetVersionPage, Problem]]:
    """Versions, highest version number first

    Args:
        dataset_id (UUID):
        limit (Union[Unset, int]):  Default: 50.
        cursor (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[DatasetVersionPage, Problem]
    """

    return (
        await asyncio_detailed(
            dataset_id=dataset_id,
            client=client,
            limit=limit,
            cursor=cursor,
        )
    ).parsed
