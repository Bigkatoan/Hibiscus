"""Tiny wrapper around the docker CLI for the deploy integration tests (real containers, no mocks).

Every resource created here carries the label ``ai.hibiscus.test=a8`` and a random suffix, so
parallel agents / CI jobs never collide and ``cleanup`` can always remove what it created.
"""

from __future__ import annotations

import json
import secrets
import shutil
import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass, field

LABEL = "ai.hibiscus.test=a8"


def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    res = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"], capture_output=True, text=True)
    return res.returncode == 0


def run(
    cmd: Sequence[str], *, input_text: str | None = None, check: bool = True, timeout: float = 600
) -> str:
    res = subprocess.run(list(cmd), input=input_text, capture_output=True, text=True, timeout=timeout)
    if check and res.returncode != 0:
        raise RuntimeError(f"command failed ({res.returncode}): {' '.join(cmd)}\n{res.stdout}\n{res.stderr}")
    return res.stdout


def suffix() -> str:
    return secrets.token_hex(4)


@dataclass
class Docker:
    """Tracks created containers/networks; ``cleanup()`` removes them all."""

    containers: list[str] = field(default_factory=list)
    networks: list[str] = field(default_factory=list)

    def network(self, name: str) -> str:
        run(["docker", "network", "create", "--label", LABEL, name])
        self.networks.append(name)
        return name

    def container(self, name: str, image: str, *args: str, cmd: Sequence[str] = ()) -> str:
        run(["docker", "run", "-d", "--name", name, "--label", LABEL, *args, image, *cmd])
        self.containers.append(name)
        return name

    def exec(self, name: str, *cmd: str, input_text: str | None = None, check: bool = True) -> str:
        flags = ["-i"] if input_text is not None else []
        return run(["docker", "exec", *flags, name, *cmd], input_text=input_text, check=check)

    def logs(self, name: str) -> str:
        res = subprocess.run(["docker", "logs", name], capture_output=True, text=True)
        return res.stdout + res.stderr

    def health(self, name: str) -> str:
        out = run(["docker", "inspect", "--format", "{{json .State}}", name])
        state = json.loads(out)
        health = state.get("Health") or {}
        return str(health.get("Status") or state.get("Status"))

    def wait_until(self, predicate_cmd: Sequence[str], *, timeout: float = 90, interval: float = 1.0) -> None:
        deadline = time.monotonic() + timeout
        last = ""
        while time.monotonic() < deadline:
            res = subprocess.run(list(predicate_cmd), capture_output=True, text=True)
            if res.returncode == 0:
                return
            last = res.stderr or res.stdout
            time.sleep(interval)
        raise TimeoutError(f"timed out waiting for {' '.join(predicate_cmd)}: {last}")

    def cleanup(self) -> None:
        for c in reversed(self.containers):
            subprocess.run(["docker", "rm", "-f", "-v", c], capture_output=True)
        for n in reversed(self.networks):
            subprocess.run(["docker", "network", "rm", n], capture_output=True)
        self.containers.clear()
        self.networks.clear()
