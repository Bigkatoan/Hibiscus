from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.policy_type import PolicyType
from ...models.problem import Problem
from ...models.run_page import RunPage
from ...models.run_status import RunStatus
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    workspace_id: UUID,
    status: list[RunStatus] | Unset = UNSET,
    dataset_id: UUID | Unset = UNSET,
    policy_type: PolicyType | Unset = UNSET,
    created_by: str | Unset = UNSET,
    q: str | Unset = UNSET,
    limit: int | Unset = 50,
    cursor: str | Unset = UNSET,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    json_workspace_id = str(workspace_id)
    params["workspace_id"] = json_workspace_id

    json_status: list[str] | Unset = UNSET
    if not isinstance(status, Unset):
        json_status = []
        for status_item_data in status:
            status_item = status_item_data.value
            json_status.append(status_item)

    params["status"] = json_status

    json_dataset_id: str | Unset = UNSET
    if not isinstance(dataset_id, Unset):
        json_dataset_id = str(dataset_id)
    params["dataset_id"] = json_dataset_id

    json_policy_type: str | Unset = UNSET
    if not isinstance(policy_type, Unset):
        json_policy_type = policy_type.value

    params["policy_type"] = json_policy_type

    params["created_by"] = created_by

    params["q"] = q

    params["limit"] = limit

    params["cursor"] = cursor

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/runs",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Problem | RunPage | None:
    if response.status_code == 200:
        response_200 = RunPage.from_dict(response.json())

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
) -> Response[Problem | RunPage]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    workspace_id: UUID,
    status: list[RunStatus] | Unset = UNSET,
    dataset_id: UUID | Unset = UNSET,
    policy_type: PolicyType | Unset = UNSET,
    created_by: str | Unset = UNSET,
    q: str | Unset = UNSET,
    limit: int | Unset = 50,
    cursor: str | Unset = UNSET,
) -> Response[Problem | RunPage]:
    """Runs in a workspace, newest first

    Args:
        workspace_id (UUID):
        status (list[RunStatus] | Unset):
        dataset_id (UUID | Unset):
        policy_type (PolicyType | Unset):
        created_by (str | Unset):
        q (str | Unset):
        limit (int | Unset):  Default: 50.
        cursor (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | RunPage]
    """

    kwargs = _get_kwargs(
        workspace_id=workspace_id,
        status=status,
        dataset_id=dataset_id,
        policy_type=policy_type,
        created_by=created_by,
        q=q,
        limit=limit,
        cursor=cursor,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    workspace_id: UUID,
    status: list[RunStatus] | Unset = UNSET,
    dataset_id: UUID | Unset = UNSET,
    policy_type: PolicyType | Unset = UNSET,
    created_by: str | Unset = UNSET,
    q: str | Unset = UNSET,
    limit: int | Unset = 50,
    cursor: str | Unset = UNSET,
) -> Problem | RunPage | None:
    """Runs in a workspace, newest first

    Args:
        workspace_id (UUID):
        status (list[RunStatus] | Unset):
        dataset_id (UUID | Unset):
        policy_type (PolicyType | Unset):
        created_by (str | Unset):
        q (str | Unset):
        limit (int | Unset):  Default: 50.
        cursor (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | RunPage
    """

    return sync_detailed(
        client=client,
        workspace_id=workspace_id,
        status=status,
        dataset_id=dataset_id,
        policy_type=policy_type,
        created_by=created_by,
        q=q,
        limit=limit,
        cursor=cursor,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    workspace_id: UUID,
    status: list[RunStatus] | Unset = UNSET,
    dataset_id: UUID | Unset = UNSET,
    policy_type: PolicyType | Unset = UNSET,
    created_by: str | Unset = UNSET,
    q: str | Unset = UNSET,
    limit: int | Unset = 50,
    cursor: str | Unset = UNSET,
) -> Response[Problem | RunPage]:
    """Runs in a workspace, newest first

    Args:
        workspace_id (UUID):
        status (list[RunStatus] | Unset):
        dataset_id (UUID | Unset):
        policy_type (PolicyType | Unset):
        created_by (str | Unset):
        q (str | Unset):
        limit (int | Unset):  Default: 50.
        cursor (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | RunPage]
    """

    kwargs = _get_kwargs(
        workspace_id=workspace_id,
        status=status,
        dataset_id=dataset_id,
        policy_type=policy_type,
        created_by=created_by,
        q=q,
        limit=limit,
        cursor=cursor,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    workspace_id: UUID,
    status: list[RunStatus] | Unset = UNSET,
    dataset_id: UUID | Unset = UNSET,
    policy_type: PolicyType | Unset = UNSET,
    created_by: str | Unset = UNSET,
    q: str | Unset = UNSET,
    limit: int | Unset = 50,
    cursor: str | Unset = UNSET,
) -> Problem | RunPage | None:
    """Runs in a workspace, newest first

    Args:
        workspace_id (UUID):
        status (list[RunStatus] | Unset):
        dataset_id (UUID | Unset):
        policy_type (PolicyType | Unset):
        created_by (str | Unset):
        q (str | Unset):
        limit (int | Unset):  Default: 50.
        cursor (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | RunPage
    """

    return (
        await asyncio_detailed(
            client=client,
            workspace_id=workspace_id,
            status=status,
            dataset_id=dataset_id,
            policy_type=policy_type,
            created_by=created_by,
            q=q,
            limit=limit,
            cursor=cursor,
        )
    ).parsed
