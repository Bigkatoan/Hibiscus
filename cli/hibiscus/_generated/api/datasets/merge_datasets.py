from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.dataset_version_accepted import DatasetVersionAccepted
from ...models.problem import Problem
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    body: Any,
    x_csrf_token: str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_csrf_token, Unset):
        headers["X-CSRF-Token"] = x_csrf_token

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/datasets/merge",
    }

    _kwargs["json"] = body

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> DatasetVersionAccepted | Problem | None:
    if response.status_code == 202:
        response_202 = DatasetVersionAccepted.from_dict(response.json())

        return response_202

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
) -> Response[DatasetVersionAccepted | Problem]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: Any,
    x_csrf_token: str | Unset = UNSET,
) -> Response[DatasetVersionAccepted | Problem]:
    """Merge ready versions with identical feature schema into a new version (lerobot-edit-dataset)

    Args:
        x_csrf_token (str | Unset):
        body (Any):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DatasetVersionAccepted | Problem]
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
    body: Any,
    x_csrf_token: str | Unset = UNSET,
) -> DatasetVersionAccepted | Problem | None:
    """Merge ready versions with identical feature schema into a new version (lerobot-edit-dataset)

    Args:
        x_csrf_token (str | Unset):
        body (Any):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DatasetVersionAccepted | Problem
    """

    return sync_detailed(
        client=client,
        body=body,
        x_csrf_token=x_csrf_token,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: Any,
    x_csrf_token: str | Unset = UNSET,
) -> Response[DatasetVersionAccepted | Problem]:
    """Merge ready versions with identical feature schema into a new version (lerobot-edit-dataset)

    Args:
        x_csrf_token (str | Unset):
        body (Any):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DatasetVersionAccepted | Problem]
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
    body: Any,
    x_csrf_token: str | Unset = UNSET,
) -> DatasetVersionAccepted | Problem | None:
    """Merge ready versions with identical feature schema into a new version (lerobot-edit-dataset)

    Args:
        x_csrf_token (str | Unset):
        body (Any):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DatasetVersionAccepted | Problem
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
            x_csrf_token=x_csrf_token,
        )
    ).parsed
