from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.policy_detail import PolicyDetail
from ...models.policy_type import PolicyType
from ...models.problem import Problem
from ...types import Response


def _get_kwargs(
    policy_type: PolicyType,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/policies/{policy_type}".format(
            policy_type=quote(str(policy_type), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> PolicyDetail | Problem | None:
    if response.status_code == 200:
        response_200 = PolicyDetail.from_dict(response.json())

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
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[PolicyDetail | Problem]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    policy_type: PolicyType,
    *,
    client: AuthenticatedClient,
) -> Response[PolicyDetail | Problem]:
    """JSON Schemas (policy + train) and presets for one policy

    Args:
        policy_type (PolicyType):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[PolicyDetail | Problem]
    """

    kwargs = _get_kwargs(
        policy_type=policy_type,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    policy_type: PolicyType,
    *,
    client: AuthenticatedClient,
) -> PolicyDetail | Problem | None:
    """JSON Schemas (policy + train) and presets for one policy

    Args:
        policy_type (PolicyType):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        PolicyDetail | Problem
    """

    return sync_detailed(
        policy_type=policy_type,
        client=client,
    ).parsed


async def asyncio_detailed(
    policy_type: PolicyType,
    *,
    client: AuthenticatedClient,
) -> Response[PolicyDetail | Problem]:
    """JSON Schemas (policy + train) and presets for one policy

    Args:
        policy_type (PolicyType):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[PolicyDetail | Problem]
    """

    kwargs = _get_kwargs(
        policy_type=policy_type,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    policy_type: PolicyType,
    *,
    client: AuthenticatedClient,
) -> PolicyDetail | Problem | None:
    """JSON Schemas (policy + train) and presets for one policy

    Args:
        policy_type (PolicyType):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        PolicyDetail | Problem
    """

    return (
        await asyncio_detailed(
            policy_type=policy_type,
            client=client,
        )
    ).parsed
