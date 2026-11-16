from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.eval_metrics import EvalMetrics
from ...models.problem import Problem
from ...types import Response


def _get_kwargs(
    run_id: UUID,
    step: int,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/runs/{run_id}/checkpoints/{step}/eval-result".format(
            run_id=quote(str(run_id), safe=""),
            step=quote(str(step), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> EvalMetrics | Problem | None:
    if response.status_code == 200:
        response_200 = EvalMetrics.from_dict(response.json())

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
) -> Response[EvalMetrics | Problem]:
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
) -> Response[EvalMetrics | Problem]:
    """Offline eval result (404 until an eval succeeded)

    Args:
        run_id (UUID):
        step (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[EvalMetrics | Problem]
    """

    kwargs = _get_kwargs(
        run_id=run_id,
        step=step,
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
) -> EvalMetrics | Problem | None:
    """Offline eval result (404 until an eval succeeded)

    Args:
        run_id (UUID):
        step (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        EvalMetrics | Problem
    """

    return sync_detailed(
        run_id=run_id,
        step=step,
        client=client,
    ).parsed


async def asyncio_detailed(
    run_id: UUID,
    step: int,
    *,
    client: AuthenticatedClient,
) -> Response[EvalMetrics | Problem]:
    """Offline eval result (404 until an eval succeeded)

    Args:
        run_id (UUID):
        step (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[EvalMetrics | Problem]
    """

    kwargs = _get_kwargs(
        run_id=run_id,
        step=step,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    run_id: UUID,
    step: int,
    *,
    client: AuthenticatedClient,
) -> EvalMetrics | Problem | None:
    """Offline eval result (404 until an eval succeeded)

    Args:
        run_id (UUID):
        step (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        EvalMetrics | Problem
    """

    return (
        await asyncio_detailed(
            run_id=run_id,
            step=step,
            client=client,
        )
    ).parsed
