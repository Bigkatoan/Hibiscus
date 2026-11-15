from http import HTTPStatus
from typing import Any, Optional, Union
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.job import Job
from ...models.problem import Problem
from ...types import UNSET, Response, Unset


def _get_kwargs(
    job_id: UUID,
    *,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_csrf_token, Unset):
        headers["X-CSRF-Token"] = x_csrf_token

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/jobs/{job_id}/cancel".format(
            job_id=job_id,
        ),
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[Job, Problem]]:
    if response.status_code == 202:
        response_202 = Job.from_dict(response.json())

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

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Response[Union[Job, Problem]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    job_id: UUID,
    *,
    client: AuthenticatedClient,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> Response[Union[Job, Problem]]:
    """Cancel a queued or running job (idempotent)

    Args:
        job_id (UUID):
        x_csrf_token (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Job, Problem]]
    """

    kwargs = _get_kwargs(
        job_id=job_id,
        x_csrf_token=x_csrf_token,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    job_id: UUID,
    *,
    client: AuthenticatedClient,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> Optional[Union[Job, Problem]]:
    """Cancel a queued or running job (idempotent)

    Args:
        job_id (UUID):
        x_csrf_token (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Job, Problem]
    """

    return sync_detailed(
        job_id=job_id,
        client=client,
        x_csrf_token=x_csrf_token,
    ).parsed


async def asyncio_detailed(
    job_id: UUID,
    *,
    client: AuthenticatedClient,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> Response[Union[Job, Problem]]:
    """Cancel a queued or running job (idempotent)

    Args:
        job_id (UUID):
        x_csrf_token (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Job, Problem]]
    """

    kwargs = _get_kwargs(
        job_id=job_id,
        x_csrf_token=x_csrf_token,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    job_id: UUID,
    *,
    client: AuthenticatedClient,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> Optional[Union[Job, Problem]]:
    """Cancel a queued or running job (idempotent)

    Args:
        job_id (UUID):
        x_csrf_token (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Job, Problem]
    """

    return (
        await asyncio_detailed(
            job_id=job_id,
            client=client,
            x_csrf_token=x_csrf_token,
        )
    ).parsed
