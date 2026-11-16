from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.problem import Problem
from ...models.upload_session import UploadSession
from ...types import Response


def _get_kwargs(
    upload_id: UUID,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/uploads/{upload_id}".format(
            upload_id=quote(str(upload_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Problem | UploadSession | None:
    if response.status_code == 200:
        response_200 = UploadSession.from_dict(response.json())

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
) -> Response[Problem | UploadSession]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    upload_id: UUID,
    *,
    client: AuthenticatedClient,
) -> Response[Problem | UploadSession]:
    """Session state incl. received parts (resume = upload the missing part numbers)

    Args:
        upload_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | UploadSession]
    """

    kwargs = _get_kwargs(
        upload_id=upload_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    upload_id: UUID,
    *,
    client: AuthenticatedClient,
) -> Problem | UploadSession | None:
    """Session state incl. received parts (resume = upload the missing part numbers)

    Args:
        upload_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | UploadSession
    """

    return sync_detailed(
        upload_id=upload_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    upload_id: UUID,
    *,
    client: AuthenticatedClient,
) -> Response[Problem | UploadSession]:
    """Session state incl. received parts (resume = upload the missing part numbers)

    Args:
        upload_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | UploadSession]
    """

    kwargs = _get_kwargs(
        upload_id=upload_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    upload_id: UUID,
    *,
    client: AuthenticatedClient,
) -> Problem | UploadSession | None:
    """Session state incl. received parts (resume = upload the missing part numbers)

    Args:
        upload_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | UploadSession
    """

    return (
        await asyncio_detailed(
            upload_id=upload_id,
            client=client,
        )
    ).parsed
