"""SEC-auth-03: the run SSE stream re-checks the caller's credential and membership while open."""

from __future__ import annotations

import dataclasses
import threading
import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import uvicorn
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import models as m
from tests.runs.conftest import PrincipalHolder, Services, World, check, make_app, run_body
from tests.runs.test_api_stream_logs_models import _free_port


@pytest.fixture
def pat_world(world: World, holder: PrincipalHolder, sync_engine: Any) -> World:
    """The world user acting through a real (revocable) runs PAT bound to the workspace."""
    tok_id = uuid.uuid4()
    with Session(sync_engine) as s:
        s.add(
            m.ApiToken(
                id=tok_id,
                user_id=world.user_id,
                workspace_id=world.workspace_id,
                name="stream",
                prefix=tok_id.hex[:8],
                token_hash=tok_id.bytes * 2,
                scopes=["runs:read", "runs:write"],
            )
        )
        s.commit()
    holder.p = dataclasses.replace(
        world.principal,
        auth_method="pat",
        token_scopes=frozenset({"runs:read", "runs:write"}),
        token_workspace_id=world.workspace_id,
        token_id=tok_id,
    )
    world.extra["token_id"] = tok_id
    return world


@pytest.fixture
def fast_recheck_server(services: Services, holder: PrincipalHolder, pat_world: World) -> Iterator[str]:
    app = make_app(holder, services)
    app.state.services.settings.sse_auth_recheck_s = 0.3
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="on")
    )
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    deadline = time.time() + 15
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/api/v1"
    server.should_exit = True
    t.join(timeout=10)


def test_run_stream_ends_when_the_token_is_revoked(
    fast_recheck_server: str, pat_world: World, sync_engine: Any
) -> None:
    rid = check(httpx.post(f"{fast_recheck_server}/runs", json=run_body(pat_world)), "/runs", "POST")["id"]

    def revoke_later() -> None:
        time.sleep(1.5)
        with Session(sync_engine) as s:
            s.execute(
                text("UPDATE api_tokens SET revoked_at = :now WHERE id = :t"),
                {"now": datetime.now(UTC), "t": pat_world.extra["token_id"]},
            )
            s.commit()

    threading.Thread(target=revoke_later, daemon=True).start()
    start = time.time()
    buf = ""
    with httpx.Client(timeout=20) as c, c.stream("GET", f"{fast_recheck_server}/runs/{rid}/events") as r:
        assert r.status_code == 200
        for chunk in r.iter_text():  # the run stays queued: only the server can end the stream
            buf += chunk
    elapsed = time.time() - start
    assert 1.4 < elapsed < 8, elapsed
    assert "event: end" not in buf  # closed for auth, not because the run finished
