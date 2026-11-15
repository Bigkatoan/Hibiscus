"""Personal Access Tokens: ``hbp_<8 alnum prefix>_<43 char base64url secret>``, stored as sha256."""

from __future__ import annotations

import re
import secrets
import string

from app.core.crypto import sha256
from app.db.models import PatScope

PAT_RE = re.compile(r"^hbp_([A-Za-z0-9]{8})_([A-Za-z0-9_-]{43})$")
_ALNUM = string.ascii_letters + string.digits

#: scope => scopes it implies (CONTRACT_NOTES D6)
IMPLIES: dict[str, frozenset[str]] = {
    PatScope.DATASETS_WRITE.value: frozenset({PatScope.DATASETS_READ.value}),
    PatScope.RUNS_WRITE.value: frozenset({PatScope.RUNS_READ.value}),
}
READ_SCOPES = frozenset({PatScope.DATASETS_READ.value, PatScope.RUNS_READ.value, PatScope.MODELS_READ.value})


def generate_pat() -> tuple[str, str]:
    """Return ``(prefix, plaintext)``."""
    prefix = "".join(secrets.choice(_ALNUM) for _ in range(8))
    return prefix, f"hbp_{prefix}_{secrets.token_urlsafe(32)}"


def parse_pat(token: str) -> str | None:
    """Return the prefix if ``token`` is well-formed, else None."""
    m = PAT_RE.match(token)
    return m.group(1) if m else None


def pat_hash(token: str) -> bytes:
    return sha256(token)


def expand_scopes(scopes: list[str] | frozenset[str]) -> frozenset[str]:
    out = set(scopes)
    for s in scopes:
        out |= IMPLIES.get(s, frozenset())
    return frozenset(out)
