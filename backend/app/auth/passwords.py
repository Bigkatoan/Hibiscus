"""argon2id hashing + password policy (min 12, weak-pattern and offline breached-list checks)."""

from __future__ import annotations

import hashlib
import itertools
import logging
from pathlib import Path

import argon2
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.errors import ErrorCode, ProblemError

log = logging.getLogger("hibiscus.passwords")

MIN_LENGTH = 12
_BUILTIN_LIST = Path(__file__).with_name("breached_passwords.txt")


class PasswordHasher:
    def __init__(
        self,
        *,
        time_cost: int = 3,
        memory_cost_kib: int = 65536,
        parallelism: int = 4,
        breached_file: str | None = None,
    ) -> None:
        self._ph = argon2.PasswordHasher(
            time_cost=time_cost,
            memory_cost=memory_cost_kib,
            parallelism=parallelism,
            type=argon2.Type.ID,
        )
        self._dummy = self._ph.hash("hibiscus-dummy-password-for-timing")
        self._breached_sha1: set[str] = set()
        self._load(_BUILTIN_LIST)
        if breached_file:
            self._load(Path(breached_file))

    def _load(self, path: Path) -> None:
        """Lines are plain passwords or 40-hex SHA-1 (HIBP format, optional ``:count`` suffix)."""
        if not path.exists():
            log.warning("breached password list not found", extra={"path": str(path)})
            return
        with path.open(encoding="utf-8", errors="ignore") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                head = line.split(":", 1)[0]
                if len(head) == 40 and all(c in "0123456789abcdefABCDEF" for c in head):
                    self._breached_sha1.add(head.upper())
                else:
                    self._breached_sha1.add(_sha1(line))

    def hash(self, password: str) -> str:
        return self._ph.hash(password)

    def verify(self, stored_hash: str, password: str) -> bool:
        try:
            return self._ph.verify(stored_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    def dummy_verify(self, password: str) -> None:
        """Burn the same time as a real verification (no user enumeration by timing)."""
        self.verify(self._dummy, password)

    def needs_rehash(self, stored_hash: str) -> bool:
        try:
            return self._ph.check_needs_rehash(stored_hash)
        except InvalidHashError:
            return True

    def is_breached(self, password: str) -> bool:
        return _sha1(password) in self._breached_sha1

    def check_policy(
        self, password: str, *, email: str | None = None, display_name: str | None = None
    ) -> None:
        """Raise 422 ``password_too_weak`` / ``password_breached``. Length is validated by the schema too."""
        weak = len(password) < MIN_LENGTH or len(set(password)) < 5
        lowered = password.lower()
        for ident in (email.split("@")[0] if email else None, display_name):
            # what remains after removing the user's own identifiers must still be substantial
            if ident and len(ident) >= 3 and len(lowered.replace(ident.lower(), "")) < 8:
                weak = True
        if _is_sequence(lowered):
            weak = True
        if weak:
            raise ProblemError(
                422,
                ErrorCode.PASSWORD_TOO_WEAK,
                errors=[
                    {"loc": ["body", "password"], "code": "password_too_weak", "message": "Password too weak"}
                ],
                params={"min_length": MIN_LENGTH},
            )
        if self.is_breached(password):
            raise ProblemError(
                422,
                ErrorCode.PASSWORD_BREACHED,
                errors=[
                    {
                        "loc": ["body", "password"],
                        "code": "password_breached",
                        "message": "Password is breached",
                    }
                ],
            )


def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode(), usedforsecurity=False).hexdigest().upper()


def _is_sequence(s: str) -> bool:
    """Monotonic runs such as ``123456789012`` / ``abcdefghijkl`` (step ±1 for the whole string)."""
    if len(s) < 2:
        return False
    steps = {ord(b) - ord(a) for a, b in itertools.pairwise(s)}
    return steps <= {1, -9} or steps <= {-1, 9}
