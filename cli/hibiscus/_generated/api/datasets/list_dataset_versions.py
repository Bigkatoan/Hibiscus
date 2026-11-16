from http import HTTPStatus
from typing import Any
from urllib.parse import quote
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
    limit: int | Unset = 50,
    cursor: str | Unset = UNSET,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    params["limit"] = limit

    params["cursor"] = cursor

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/datasets/{dataset_id}/versions".format(
            dataset_id=quote(str(dataset_id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> DatasetVersionPage | Problem | None:
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
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[DatasetVersionPage | Problem]:
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
    limit: int | Unset = 50,
    cursor: str | Unset = UNSET,
) -> Response[DatasetVersionPage | Problem]:
    """Versions, highest version number first

    Args:
        dataset_id (UUID):
        limit (int | Unset):  Default: 50.
        cursor (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DatasetVersionPage | Problem]
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
    limit: int | Unset = 50,
    cursor: str | Unset = UNSET,
) -> DatasetVersionPage | Problem | None:
    """Versions, highest version number first

    Args:
        dataset_id (UUID):
        limit (int | Unset):  Default: 50.
        cursor (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DatasetVersionPage | Problem
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
    limit: int | Unset = 50,
    cursor: str | Unset = UNSET,
) -> Response[DatasetVersionPage | Problem]:
    """Versions, highest version number first

    Args:
        dataset_id (UUID):
        limit (int | Unset):  Default: 50.
        cursor (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DatasetVersionPage | Problem]
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
    limit: int | Unset = 50,
    cursor: str | Unset = UNSET,
) -> DatasetVersionPage | Problem | None:
    """Versions, highest version number first

    Args:
        dataset_id (UUID):
        limit (int | Unset):  Default: 50.
        cursor (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DatasetVersionPage | Problem
    """

    return (
        await asyncio_detailed(
            dataset_id=dataset_id,
            client=client,
            limit=limit,
            cursor=cursor,
        )
    ).parsed
