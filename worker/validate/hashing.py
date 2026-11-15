"""sha256 helpers and the dataset content hash (docs/db-schema.md "content_hash")."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

CHUNK = 4 * 1024 * 1024


def sha256_file(path: Path, progress: Callable[[int], None] | None = None) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(CHUNK)
            if not block:
                break
            h.update(block)
            if progress is not None:
                progress(len(block))
    return h.hexdigest()


@dataclass(frozen=True, slots=True)
class FileEntry:
    path: str  # relative, "/"-separated
    size: int
    sha256: str


def list_files(root: Path) -> list[Path]:
    """Regular files below ``root`` (sorted by relative POSIX path). Symlinks are never followed."""
    out: list[Path] = []
    for p in root.rglob("*"):
        if p.is_symlink():
            raise ValueError(f"symlink in dataset tree: {p}")
        if p.is_file():
            out.append(p)
    out.sort(key=lambda p: p.relative_to(root).as_posix())
    return out


def hash_tree(root: Path) -> tuple[str, list[FileEntry]]:
    """Return (content_hash, entries).

    content_hash = sha256 over the sorted lines ``<relative path>\\0<sha256(file)>\\n``.
    """
    entries = [
        FileEntry(p.relative_to(root).as_posix(), p.stat().st_size, sha256_file(p)) for p in list_files(root)
    ]
    h = hashlib.sha256()
    for e in entries:
        h.update(e.path.encode("utf-8") + b"\0" + e.sha256.encode("ascii") + b"\n")
    return h.hexdigest(), entries
