"""Local HTTPS webhook receiver (self-signed CA + leaf for ``hook.test``) and app factory."""

from __future__ import annotations

import datetime as dt
import ipaddress
import json
import ssl
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from app.notifications.egress import system_resolve

HOOK_HOST = "hook.test"


def make_tls(tmp: Path) -> tuple[Path, Path, Path]:
    """(ca.pem, leaf.pem, leaf.key) — CA-signed leaf for hook.test / localhost / 127.0.0.1."""
    now = dt.datetime.now(dt.UTC)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Hibiscus Test CA")])
    ca = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=2))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    key = ec.generate_private_key(ec.SECP256R1())
    leaf = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, HOOK_HOST)]))
        .issuer_name(ca_name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=2))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName(HOOK_HOST),
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False
        )
        .sign(ca_key, hashes.SHA256())
    )
    ca_pem, leaf_pem, key_pem = tmp / "ca.pem", tmp / "leaf.pem", tmp / "leaf.key"
    ca_pem.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    leaf_pem.write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    key_pem.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    )
    return ca_pem, leaf_pem, key_pem


@dataclass
class Received:
    path: str
    headers: dict[str, str]
    body: Any


@dataclass
class HookServer:
    """Threaded HTTPS server on 127.0.0.1:<ephemeral>. ``responder(path) -> (status, headers, body)``."""

    ca: Path
    port: int = 0
    received: list[Received] = field(default_factory=list)
    responder: Callable[[str], tuple[int, dict[str, str], bytes]] = field(
        default=lambda _p: (200, {}, b'{"ok":true}')
    )
    _srv: ThreadingHTTPServer | None = None

    def url(self, path: str, host: str = HOOK_HOST) -> str:
        return f"https://{host}:{self.port}{path}"

    def start(self, leaf: Path, key: Path) -> HookServer:
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                return

            def do_POST(self) -> None:
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n)
                try:
                    body: Any = json.loads(raw)
                except ValueError:
                    body = raw
                outer.received.append(
                    Received(self.path, {k.lower(): v for k, v in self.headers.items()}, body)
                )
                status, headers, payload = outer.responder(self.path)
                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(str(leaf), str(key))
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
        self.port = int(srv.server_address[1])
        self._srv = srv
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return self

    def stop(self) -> None:
        if self._srv is not None:
            self._srv.shutdown()
            self._srv.server_close()


def fake_dns(mapping: dict[str, list[str]]) -> Callable[[str, int], Any]:
    async def resolve(host: str, port: int) -> list[str]:
        if host in mapping:
            return list(mapping[host])
        return await system_resolve(host, port)

    return resolve


TEST_DNS = {
    HOOK_HOST: ["127.0.0.1"],
    "private.test": ["10.1.2.3"],
    "mixed.test": ["93.184.215.14", "192.168.1.10"],
    "cgnat.test": ["100.64.1.1"],
    "v6local.test": ["fd00::1"],
    "public.test": ["93.184.215.14"],
}
