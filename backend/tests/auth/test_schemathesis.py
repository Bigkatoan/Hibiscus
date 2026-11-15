"""Property-based contract fuzzing (schemathesis 4) of the unauthenticated auth endpoints against
api/openapi.yaml, through the real ASGI app + real Postgres/Redis. Authenticated endpoints are
covered by the example-based tests, whose every response is schema-validated (openapi_check)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import hypothesis
import pytest
import schemathesis

from app.main import create_app
from tests.auth.fixtures import Infra, make_settings, reset_db

SPEC = Path(__file__).resolve().parents[3] / "api" / "openapi.yaml"
PUBLIC_OPS = [
    "getAuthConfig",
    "login",
    "loginSecondFactor",
    "forgotPassword",
    "resetPassword",
    "verifyEmail",
    "getInvitePreview",
    "registerWithInvite",
    "refreshSession",
    "healthz",
]
# Random tokens are schema-valid but semantically unknown: the contract answers 400
# one_time_token_invalid / 404 invite_invalid, which the "positive data accepted" heuristic flags.
# registerWithInvite answers 404 invite_invalid, not yet documented (CR-A2-4, CONTRACT_NOTES.md).
EXCLUDED: dict[str, list[object]] = {
    "resetPassword": [schemathesis.checks.positive_data_acceptance],
    "verifyEmail": [schemathesis.checks.positive_data_acceptance],
    "registerWithInvite": [
        schemathesis.checks.positive_data_acceptance,
        schemathesis.checks.status_code_conformance,
    ],
}


@pytest.mark.parametrize("operation_id", PUBLIC_OPS)
def test_public_operations_conform(containers: Infra, operation_id: str) -> None:
    asyncio.run(reset_db(containers.pg_url))
    app = create_app(make_settings(rate_limit_enabled=False))
    schema = schemathesis.openapi.from_path(SPEC)
    schema.app = app
    op = schema.find_operation_by_id(operation_id)

    @hypothesis.given(case=op.as_strategy())
    @hypothesis.settings(
        max_examples=30,
        deadline=None,
        derandomize=True,
        suppress_health_check=list(hypothesis.HealthCheck),
        database=None,
    )
    def run(case: schemathesis.Case[Any]) -> None:
        response = case.call_and_validate(excluded_checks=EXCLUDED.get(operation_id, []))  # type: ignore[arg-type]
        assert response.status_code < 500

    run()
