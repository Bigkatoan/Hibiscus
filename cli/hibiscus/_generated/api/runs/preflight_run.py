from http import HTTPStatus
from typing import Any, Optional, Union

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.preflight_report import PreflightReport
from ...models.problem import Problem
from ...models.run_create import RunCreate
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    body: RunCreate,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_csrf_token, Unset):
        headers["X-CSRF-Token"] = x_csrf_token

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/runs/preflight",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[PreflightReport, Problem]]:
    if response.status_code == 200:
        response_200 = PreflightReport.from_dict(response.json())

        return response_200

    if response.status_code == 401:
        response_401 = Problem.from_dict(response.json())

        return response_401

    if response.status_code == 404:
        response_404 = Problem.from_dict(response.json())

        return response_404

    if response.status_code == 422:
        response_422 = Problem.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Response[Union[PreflightReport, Problem]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: RunCreate,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> Response[Union[PreflightReport, Problem]]:
    """Validate a RunCreate without creating it; returns checks, estimate, resolved config

     Always 200 when the body is schema-valid; blockers are reported in `checks` with
    `severity=error`. The resource estimate may be `source=pending` while a dry-run job is
    measuring it (poll again, or listen on the workspace stream for `estimate.ready`).

    Args:
        x_csrf_token (Union[Unset, str]):
        body (RunCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[PreflightReport, Problem]]
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
    body: RunCreate,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> Optional[Union[PreflightReport, Problem]]:
    """Validate a RunCreate without creating it; returns checks, estimate, resolved config

     Always 200 when the body is schema-valid; blockers are reported in `checks` with
    `severity=error`. The resource estimate may be `source=pending` while a dry-run job is
    measuring it (poll again, or listen on the workspace stream for `estimate.ready`).

    Args:
        x_csrf_token (Union[Unset, str]):
        body (RunCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[PreflightReport, Problem]
    """

    return sync_detailed(
        client=client,
        body=body,
        x_csrf_token=x_csrf_token,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: RunCreate,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> Response[Union[PreflightReport, Problem]]:
    """Validate a RunCreate without creating it; returns checks, estimate, resolved config

     Always 200 when the body is schema-valid; blockers are reported in `checks` with
    `severity=error`. The resource estimate may be `source=pending` while a dry-run job is
    measuring it (poll again, or listen on the workspace stream for `estimate.ready`).

    Args:
        x_csrf_token (Union[Unset, str]):
        body (RunCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[PreflightReport, Problem]]
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
    body: RunCreate,
    x_csrf_token: Union[Unset, str] = UNSET,
) -> Optional[Union[PreflightReport, Problem]]:
    """Validate a RunCreate without creating it; returns checks, estimate, resolved config

     Always 200 when the body is schema-valid; blockers are reported in `checks` with
    `severity=error`. The resource estimate may be `source=pending` while a dry-run job is
    measuring it (poll again, or listen on the workspace stream for `estimate.ready`).

    Args:
        x_csrf_token (Union[Unset, str]):
        body (RunCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[PreflightReport, Problem]
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
            x_csrf_token=x_csrf_token,
        )
    ).parsed
