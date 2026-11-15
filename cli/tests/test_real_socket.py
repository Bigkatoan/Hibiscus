"""Over-the-wire checks with a real HTTP server on 127.0.0.1 (ephemeral port, never 8000/18000).

respx short-circuits the transport; these tests make sure the same code works with real sockets:
SSE framing split across TCP reads, an abrupt connection drop, a silent (heartbeat-less) connection
detected by the read timeout, and an upload part sent with Content-Length (no chunked encoding).
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, ClassVar

import pytest

from hibiscus.api import Backoff, HibiscusApi
from hibiscus.sse import RunEventStream

RUN = "11111111-1111-1111-1111-111111111111"


class Handler(BaseHTTPRequestHandler):
    connections: ClassVar[list[dict[str, Any]]] = []
    parts: ClassVar[list[dict[str, Any]]] = []
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def do_GET(self) -> None:
        n = len(self.connections)
        self.connections.append({"last_event_id": self.headers.get("Last-Event-ID"), "path": self.path})
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        if n == 0:
            # frames split mid-line across writes, then an abrupt close (no `end`)
            self.wfile.write(b"retry: 50\n\nid: 1\nevent: sta")
            self.wfile.flush()
            time.sleep(0.05)
            self.wfile.write(b'tus\ndata: {"to": "running"}\n\nid: 2\nevent: metrics\ndata: {"step": 1}\n\n')
            self.wfile.flush()
            self.connection.shutdown(2)
        elif n == 1:
            # goes silent: the client must notice via its read timeout and reconnect
            self.wfile.write(b'id: 3\nevent: metrics\ndata: {"step": 2}\n\n')
            self.wfile.flush()
            time.sleep(1.5)
        else:
            self.wfile.write(b'event: heartbeat\ndata: {"kind": "heartbeat"}\n\n')
            self.wfile.write(b'event: end\ndata: {"kind": "end", "final_status": "succeeded"}\n\n')
            self.wfile.flush()

    def do_PUT(self) -> None:
        length = int(self.headers["Content-Length"])
        body = self.rfile.read(length)
        self.parts.append(
            {
                "te": self.headers.get("Transfer-Encoding"),
                "len": length,
                "sha_ok": hashlib.sha256(body).hexdigest() == self.headers["X-Content-SHA256"],
                "auth": self.headers.get("Authorization"),
            }
        )
        out = json.dumps(
            {"part_number": 1, "size": length, "sha256": hashlib.sha256(body).hexdigest()}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


@pytest.fixture
def server() -> Iterator[str]:
    Handler.connections = []
    Handler.parts = []
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    assert port not in (8000, 18000)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}/api/v1"
    httpd.shutdown()
    httpd.server_close()


def test_sse_over_socket_reconnects_after_drop_and_silence(server: str) -> None:
    with HibiscusApi(server, "hbp_AbCd1234_" + "x" * 43, backoff=Backoff(sleep=lambda s: None)) as api:
        why: list[str] = []
        stream = RunEventStream(
            api, RUN, read_timeout=0.5, sleep=lambda s: None, on_reconnect=lambda n, w, d: why.append(w)
        )
        seen = [(m.event, m.id, m.json()) for m in stream]
    assert seen == [
        ("status", "1", {"to": "running"}),
        ("metrics", "2", {"step": 1}),
        ("metrics", "3", {"step": 2}),
        ("heartbeat", None, {"kind": "heartbeat"}),
        ("end", None, {"kind": "end", "final_status": "succeeded"}),
    ]
    assert [c["last_event_id"] for c in Handler.connections] == [None, "2", "3"]
    assert "ReadTimeout" in why[1]


def test_upload_part_over_socket_uses_content_length(server: str) -> None:
    data = b"\x00\x01" * 300_000
    with HibiscusApi(server, "hbp_AbCd1234_" + "x" * 43) as api:
        body = api.upload_part(RUN, 1, data, hashlib.sha256(data).hexdigest())
    assert body["size"] == len(data)
    (p,) = Handler.parts
    assert p == {"te": None, "len": len(data), "sha_ok": True, "auth": "Bearer hbp_AbCd1234_" + "x" * 43}
