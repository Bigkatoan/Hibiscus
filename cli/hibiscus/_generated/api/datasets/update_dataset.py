from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.dataset import Dataset
from ...models.dataset_update import DatasetUpdate
from ...models.problem import Problem
from ...types import UNSET, Response, Unset


def _get_kwargs(
    dataset_id: UUID,
    *,
    body: DatasetUpdate,
    x_csrf_token: str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_csrf_token, Unset):
        headers["X-CSRF-Token"] = x_csrf_token

    _kwargs: dict[str, Any] = {
        "method": "patch",
        "url": "/datasets/{dataset_id}".format(
            dataset_id=quote(str(dataset_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Dataset | Problem | None:
    if response.status_code == 200:
        response_200 = Dataset.from_dict(response.json())

        return response_200

    if response.status_code == 401:
        response_401 = Problem.from_dict(response.json())

        return response_401

    if response.status_code == 403:
        response_403 = Problem.from_dict(response.json())

        return response_403

    if response.status_code == 404:
        response_404 = Problem.from_dict(response.json())

        return response_404

    if response.status_code == 409:
        response_409 = Problem.from_dict(response.json())

        return response_409

    if response.status_code == 422:
        response_422 = Problem.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Dataset | Problem]:
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
    body: DatasetUpdate,
    x_csrf_token: str | Unset = UNSET,
) -> Response[Dataset | Problem]:
    """Rename / edit description (member+)

    Args:
        dataset_id (UUID):
        x_csrf_token (str | Unset):
        body (DatasetUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Dataset | Problem]
    """

    kwargs = _get_kwargs(
        dataset_id=dataset_id,
        body=body,
        x_csrf_token=x_csrf_token,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    dataset_id: UUID,
    *,
    client: AuthenticatedClient,
    body: DatasetUpdate,
    x_csrf_token: str | Unset = UNSET,
) -> Dataset | Problem | None:
    """Rename / edit description (member+)

    Args:
        dataset_id (UUID):
        x_csrf_token (str | Unset):
        body (DatasetUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Dataset | Problem
    """

    return sync_detailed(
        dataset_id=dataset_id,
        client=client,
        body=body,
        x_csrf_token=x_csrf_token,
    ).parsed


async def asyncio_detailed(
    dataset_id: UUID,
    *,
    client: AuthenticatedClient,
    body: DatasetUpdate,
    x_csrf_token: str | Unset = UNSET,
) -> Response[Dataset | Problem]:
    """Rename / edit description (member+)

    Args:
        dataset_id (UUID):
        x_csrf_token (str | Unset):
        body (DatasetUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Dataset | Problem]
    """

    kwargs = _get_kwargs(
        dataset_id=dataset_id,
        body=body,
        x_csrf_token=x_csrf_token,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    dataset_id: UUID,
    *,
    client: AuthenticatedClient,
    body: DatasetUpdate,
    x_csrf_token: str | Unset = UNSET,
) -> Dataset | Problem | None:
    """Rename / edit description (member+)

    Args:
        dataset_id (UUID):
        x_csrf_token (str | Unset):
        body (DatasetUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Dataset | Problem
    """

    return (
        await asyncio_detailed(
            dataset_id=dataset_id,
            client=client,
            body=body,
            x_csrf_token=x_csrf_token,
        )
    ).parsed
