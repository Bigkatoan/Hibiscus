from http import HTTPStatus
from typing import Any, Optional, Union
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.problem import Problem
from ...models.validation_report import ValidationReport
from ...types import Response


def _get_kwargs(
    version_id: UUID,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/dataset-versions/{version_id}/validation".format(
            version_id=version_id,
        ),
    }

    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[Problem, ValidationReport]]:
    if response.status_code == 200:
        response_200 = ValidationReport.from_dict(response.json())

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
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Response[Union[Problem, ValidationReport]]:
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
) -> Response[Union[Problem, ValidationReport]]:
    """Full step-by-step validation report (404 until validation started)

    Args:
        version_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Problem, ValidationReport]]
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
) -> Optional[Union[Problem, ValidationReport]]:
    """Full step-by-step validation report (404 until validation started)

    Args:
        version_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Problem, ValidationReport]
    """

    return sync_detailed(
        version_id=version_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    version_id: UUID,
    *,
    client: AuthenticatedClient,
) -> Response[Union[Problem, ValidationReport]]:
    """Full step-by-step validation report (404 until validation started)

    Args:
        version_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Problem, ValidationReport]]
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
) -> Optional[Union[Problem, ValidationReport]]:
    """Full step-by-step validation report (404 until validation started)

    Args:
        version_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Problem, ValidationReport]
    """

    return (
        await asyncio_detailed(
            version_id=version_id,
            client=client,
        )
    ).parsed
