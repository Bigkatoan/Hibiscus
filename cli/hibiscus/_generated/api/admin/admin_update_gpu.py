from http import HTTPStatus
from typing import Any, Optional, Union

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.admin_update_gpu_body import AdminUpdateGpuBody
from ...models.gpu_node import GpuNode
from ...models.problem import Problem
from ...types import UNSET, Response, Unset


def _get_kwargs(
    gpu_id: str,
    *,
    body: AdminUpdateGpuBody,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_csrf_token, Unset):
        headers["X-CSRF-Token"] = x_csrf_token

    _kwargs: dict[str, Any] = {
        "method": "patch",
        "url": "/admin/gpus/{gpu_id}".format(
            gpu_id=gpu_id,
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[GpuNode, Problem]]:
    if response.status_code == 200:
        response_200 = GpuNode.from_dict(response.json())

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

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Response[Union[GpuNode, Problem]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    gpu_id: str,
    *,
    client: Union[AuthenticatedClient, Client],
    body: AdminUpdateGpuBody,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> Response[Union[GpuNode, Problem]]:
    """Drain (finish current run, take no new ones), disable or re-enable a GPU

    Args:
        gpu_id (str):
        x_csrf_token (Union[Unset, str]):
        body (AdminUpdateGpuBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[GpuNode, Problem]]
    """

    kwargs = _get_kwargs(
        gpu_id=gpu_id,
        body=body,
        x_csrf_token=x_csrf_token,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    gpu_id: str,
    *,
    client: Union[AuthenticatedClient, Client],
    body: AdminUpdateGpuBody,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> Optional[Union[GpuNode, Problem]]:
    """Drain (finish current run, take no new ones), disable or re-enable a GPU

    Args:
        gpu_id (str):
        x_csrf_token (Union[Unset, str]):
        body (AdminUpdateGpuBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[GpuNode, Problem]
    """

    return sync_detailed(
        gpu_id=gpu_id,
        client=client,
        body=body,
        x_csrf_token=x_csrf_token,
    ).parsed


async def asyncio_detailed(
    gpu_id: str,
    *,
    client: Union[AuthenticatedClient, Client],
    body: AdminUpdateGpuBody,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> Response[Union[GpuNode, Problem]]:
    """Drain (finish current run, take no new ones), disable or re-enable a GPU

    Args:
        gpu_id (str):
        x_csrf_token (Union[Unset, str]):
        body (AdminUpdateGpuBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[GpuNode, Problem]]
    """

    kwargs = _get_kwargs(
        gpu_id=gpu_id,
        body=body,
        x_csrf_token=x_csrf_token,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    gpu_id: str,
    *,
    client: Union[AuthenticatedClient, Client],
    body: AdminUpdateGpuBody,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> Optional[Union[GpuNode, Problem]]:
    """Drain (finish current run, take no new ones), disable or re-enable a GPU

    Args:
        gpu_id (str):
        x_csrf_token (Union[Unset, str]):
        body (AdminUpdateGpuBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[GpuNode, Problem]
    """

    return (
        await asyncio_detailed(
            gpu_id=gpu_id,
            client=client,
            body=body,
            x_csrf_token=x_csrf_token,
        )
    ).parsed
