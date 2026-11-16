from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.dataset_version import DatasetVersion
from ...models.problem import Problem
from ...types import Response


def _get_kwargs(
    version_id: UUID,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/dataset-versions/{version_id}".format(
            version_id=quote(str(version_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> DatasetVersion | Problem | None:
    if response.status_code == 200:
        response_200 = DatasetVersion.from_dict(response.json())

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
) -> Response[DatasetVersion | Problem]:
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
) -> Response[DatasetVersion | Problem]:
    """One version (schema, stats summary, status, validation summary)

    Args:
        version_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DatasetVersion | Problem]
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
) -> DatasetVersion | Problem | None:
    """One version (schema, stats summary, status, validation summary)

    Args:
        version_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DatasetVersion | Problem
    """

    return sync_detailed(
        version_id=version_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    version_id: UUID,
    *,
    client: AuthenticatedClient,
) -> Response[DatasetVersion | Problem]:
    """One version (schema, stats summary, status, validation summary)

    Args:
        version_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DatasetVersion | Problem]
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
) -> DatasetVersion | Problem | None:
    """One version (schema, stats summary, status, validation summary)

    Args:
        version_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DatasetVersion | Problem
    """

    return (
        await asyncio_detailed(
            version_id=version_id,
            client=client,
        )
    ).parsed
