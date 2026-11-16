from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.problem import Problem
from ...models.run import Run
from ...models.run_resume_request import RunResumeRequest
from ...types import UNSET, Response, Unset


def _get_kwargs(
    run_id: UUID,
    *,
    body: RunResumeRequest | Unset = UNSET,
    x_csrf_token: str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_csrf_token, Unset):
        headers["X-CSRF-Token"] = x_csrf_token

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/runs/{run_id}/resume".format(
            run_id=quote(str(run_id), safe=""),
        ),
    }

    if not isinstance(body, Unset):
        _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Problem | Run | None:
    if response.status_code == 202:
        response_202 = Run.from_dict(response.json())

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
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Problem | Run]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    run_id: UUID,
    *,
    client: AuthenticatedClient,
    body: RunResumeRequest | Unset = UNSET,
    x_csrf_token: str | Unset = UNSET,
) -> Response[Problem | Run]:
    """Re-queue a paused run, or a failed run that has a checkpoint, resuming from checkpoints/last

    Args:
        run_id (UUID):
        x_csrf_token (str | Unset):
        body (RunResumeRequest | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | Run]
    """

    kwargs = _get_kwargs(
        run_id=run_id,
        body=body,
        x_csrf_token=x_csrf_token,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    run_id: UUID,
    *,
    client: AuthenticatedClient,
    body: RunResumeRequest | Unset = UNSET,
    x_csrf_token: str | Unset = UNSET,
) -> Problem | Run | None:
    """Re-queue a paused run, or a failed run that has a checkpoint, resuming from checkpoints/last

    Args:
        run_id (UUID):
        x_csrf_token (str | Unset):
        body (RunResumeRequest | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | Run
    """

    return sync_detailed(
        run_id=run_id,
        client=client,
        body=body,
        x_csrf_token=x_csrf_token,
    ).parsed


async def asyncio_detailed(
    run_id: UUID,
    *,
    client: AuthenticatedClient,
    body: RunResumeRequest | Unset = UNSET,
    x_csrf_token: str | Unset = UNSET,
) -> Response[Problem | Run]:
    """Re-queue a paused run, or a failed run that has a checkpoint, resuming from checkpoints/last

    Args:
        run_id (UUID):
        x_csrf_token (str | Unset):
        body (RunResumeRequest | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | Run]
    """

    kwargs = _get_kwargs(
        run_id=run_id,
        body=body,
        x_csrf_token=x_csrf_token,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    run_id: UUID,
    *,
    client: AuthenticatedClient,
    body: RunResumeRequest | Unset = UNSET,
    x_csrf_token: str | Unset = UNSET,
) -> Problem | Run | None:
    """Re-queue a paused run, or a failed run that has a checkpoint, resuming from checkpoints/last

    Args:
        run_id (UUID):
        x_csrf_token (str | Unset):
        body (RunResumeRequest | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | Run
    """

    return (
        await asyncio_detailed(
            run_id=run_id,
            client=client,
            body=body,
            x_csrf_token=x_csrf_token,
        )
    ).parsed
