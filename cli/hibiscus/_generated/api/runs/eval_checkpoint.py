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
    run_id: UUID,
    step: int,
    *,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_csrf_token, Unset):
        headers["X-CSRF-Token"] = x_csrf_token

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/runs/{run_id}/checkpoints/{step}/eval".format(
            run_id=run_id,
            step=step,
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

    if response.status_code == 409:
        response_409 = Problem.from_dict(response.json())

        return response_409

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
    run_id: UUID,
    step: int,
    *,
    client: AuthenticatedClient,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> Response[Union[Job, Problem]]:
    """Run offline held-out evaluation for a checkpoint

     GPU job: refused with 403 `quota_exceeded` when the requester's monthly GPU hours are used up
    (`params.reason=gpu_hours`) or when `max_concurrent_runs` export/eval jobs of the requester are
    already queued or running (`params.reason=concurrent_jobs`). The job's GPU time counts toward the
    monthly GPU hours.

    Args:
        run_id (UUID):
        step (int):
        x_csrf_token (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Job, Problem]]
    """

    kwargs = _get_kwargs(
        run_id=run_id,
        step=step,
        x_csrf_token=x_csrf_token,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    run_id: UUID,
    step: int,
    *,
    client: AuthenticatedClient,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> Optional[Union[Job, Problem]]:
    """Run offline held-out evaluation for a checkpoint

     GPU job: refused with 403 `quota_exceeded` when the requester's monthly GPU hours are used up
    (`params.reason=gpu_hours`) or when `max_concurrent_runs` export/eval jobs of the requester are
    already queued or running (`params.reason=concurrent_jobs`). The job's GPU time counts toward the
    monthly GPU hours.

    Args:
        run_id (UUID):
        step (int):
        x_csrf_token (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Job, Problem]
    """

    return sync_detailed(
        run_id=run_id,
        step=step,
        client=client,
        x_csrf_token=x_csrf_token,
    ).parsed


async def asyncio_detailed(
    run_id: UUID,
    step: int,
    *,
    client: AuthenticatedClient,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> Response[Union[Job, Problem]]:
    """Run offline held-out evaluation for a checkpoint

     GPU job: refused with 403 `quota_exceeded` when the requester's monthly GPU hours are used up
    (`params.reason=gpu_hours`) or when `max_concurrent_runs` export/eval jobs of the requester are
    already queued or running (`params.reason=concurrent_jobs`). The job's GPU time counts toward the
    monthly GPU hours.

    Args:
        run_id (UUID):
        step (int):
        x_csrf_token (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Job, Problem]]
    """

    kwargs = _get_kwargs(
        run_id=run_id,
        step=step,
        x_csrf_token=x_csrf_token,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    run_id: UUID,
    step: int,
    *,
    client: AuthenticatedClient,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> Optional[Union[Job, Problem]]:
    """Run offline held-out evaluation for a checkpoint

     GPU job: refused with 403 `quota_exceeded` when the requester's monthly GPU hours are used up
    (`params.reason=gpu_hours`) or when `max_concurrent_runs` export/eval jobs of the requester are
    already queued or running (`params.reason=concurrent_jobs`). The job's GPU time counts toward the
    monthly GPU hours.

    Args:
        run_id (UUID):
        step (int):
        x_csrf_token (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Job, Problem]
    """

    return (
        await asyncio_detailed(
            run_id=run_id,
            step=step,
            client=client,
            x_csrf_token=x_csrf_token,
        )
    ).parsed
