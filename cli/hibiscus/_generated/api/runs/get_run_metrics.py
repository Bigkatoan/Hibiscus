from http import HTTPStatus
from typing import Any, Optional, Union
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.get_run_metrics_format import GetRunMetricsFormat
from ...models.metric_series_set import MetricSeriesSet
from ...models.problem import Problem
from ...types import UNSET, Response, Unset


def _get_kwargs(
    run_id: UUID,
    *,
    keys: Union[Unset, list[str]] = UNSET,
    from_step: Union[Unset, int] = UNSET,
    to_step: Union[Unset, int] = UNSET,
    max_points: Union[Unset, int] = 2000,
    format_: Union[Unset, GetRunMetricsFormat] = GetRunMetricsFormat.JSON,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    json_keys: Union[Unset, list[str]] = UNSET
    if not isinstance(keys, Unset):
        json_keys = keys

    params["keys"] = json_keys

    params["from_step"] = from_step

    params["to_step"] = to_step

    params["max_points"] = max_points

    json_format_: Union[Unset, str] = UNSET
    if not isinstance(format_, Unset):
        json_format_ = format_.value

    params["format"] = json_format_

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/runs/{run_id}/metrics".format(
            run_id=run_id,
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[MetricSeriesSet, Problem]]:
    if response.status_code == 200:
        response_200 = MetricSeriesSet.from_dict(response.json())

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
) -> Response[Union[MetricSeriesSet, Problem]]:
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
    keys: Union[Unset, list[str]] = UNSET,
    from_step: Union[Unset, int] = UNSET,
    to_step: Union[Unset, int] = UNSET,
    max_points: Union[Unset, int] = 2000,
    format_: Union[Unset, GetRunMetricsFormat] = GetRunMetricsFormat.JSON,
) -> Response[Union[MetricSeriesSet, Problem]]:
    """Metric series by step (LTTB-downsampled to max_points per key)

    Args:
        run_id (UUID):
        keys (Union[Unset, list[str]]):
        from_step (Union[Unset, int]):
        to_step (Union[Unset, int]):
        max_points (Union[Unset, int]):  Default: 2000.
        format_ (Union[Unset, GetRunMetricsFormat]):  Default: GetRunMetricsFormat.JSON.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[MetricSeriesSet, Problem]]
    """

    kwargs = _get_kwargs(
        run_id=run_id,
        keys=keys,
        from_step=from_step,
        to_step=to_step,
        max_points=max_points,
        format_=format_,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    run_id: UUID,
    *,
    client: AuthenticatedClient,
    keys: Union[Unset, list[str]] = UNSET,
    from_step: Union[Unset, int] = UNSET,
    to_step: Union[Unset, int] = UNSET,
    max_points: Union[Unset, int] = 2000,
    format_: Union[Unset, GetRunMetricsFormat] = GetRunMetricsFormat.JSON,
) -> Optional[Union[MetricSeriesSet, Problem]]:
    """Metric series by step (LTTB-downsampled to max_points per key)

    Args:
        run_id (UUID):
        keys (Union[Unset, list[str]]):
        from_step (Union[Unset, int]):
        to_step (Union[Unset, int]):
        max_points (Union[Unset, int]):  Default: 2000.
        format_ (Union[Unset, GetRunMetricsFormat]):  Default: GetRunMetricsFormat.JSON.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[MetricSeriesSet, Problem]
    """

    return sync_detailed(
        run_id=run_id,
        client=client,
        keys=keys,
        from_step=from_step,
        to_step=to_step,
        max_points=max_points,
        format_=format_,
    ).parsed


async def asyncio_detailed(
    run_id: UUID,
    *,
    client: AuthenticatedClient,
    keys: Union[Unset, list[str]] = UNSET,
    from_step: Union[Unset, int] = UNSET,
    to_step: Union[Unset, int] = UNSET,
    max_points: Union[Unset, int] = 2000,
    format_: Union[Unset, GetRunMetricsFormat] = GetRunMetricsFormat.JSON,
) -> Response[Union[MetricSeriesSet, Problem]]:
    """Metric series by step (LTTB-downsampled to max_points per key)

    Args:
        run_id (UUID):
        keys (Union[Unset, list[str]]):
        from_step (Union[Unset, int]):
        to_step (Union[Unset, int]):
        max_points (Union[Unset, int]):  Default: 2000.
        format_ (Union[Unset, GetRunMetricsFormat]):  Default: GetRunMetricsFormat.JSON.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[MetricSeriesSet, Problem]]
    """

    kwargs = _get_kwargs(
        run_id=run_id,
        keys=keys,
        from_step=from_step,
        to_step=to_step,
        max_points=max_points,
        format_=format_,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    run_id: UUID,
    *,
    client: AuthenticatedClient,
    keys: Union[Unset, list[str]] = UNSET,
    from_step: Union[Unset, int] = UNSET,
    to_step: Union[Unset, int] = UNSET,
    max_points: Union[Unset, int] = 2000,
    format_: Union[Unset, GetRunMetricsFormat] = GetRunMetricsFormat.JSON,
) -> Optional[Union[MetricSeriesSet, Problem]]:
    """Metric series by step (LTTB-downsampled to max_points per key)

    Args:
        run_id (UUID):
        keys (Union[Unset, list[str]]):
        from_step (Union[Unset, int]):
        to_step (Union[Unset, int]):
        max_points (Union[Unset, int]):  Default: 2000.
        format_ (Union[Unset, GetRunMetricsFormat]):  Default: GetRunMetricsFormat.JSON.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[MetricSeriesSet, Problem]
    """

    return (
        await asyncio_detailed(
            run_id=run_id,
            client=client,
            keys=keys,
            from_step=from_step,
            to_step=to_step,
            max_points=max_points,
            format_=format_,
        )
    ).parsed
