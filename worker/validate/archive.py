"""Safe archive extraction through libarchive (zip, tar, tar.gz, tar.zst, rar incl. RAR5).

Guards (PLAN 3.2 "Giải nén an toàn"):
* path traversal: absolute paths, drive letters, ``..`` components, NUL / control characters,
  over-long paths or too-deep trees are rejected (``archive_unsafe_path``);
* links: symlinks and hard links are rejected (``archive_symlink``); device nodes, FIFOs and
  sockets are rejected (``archive_unsafe_path``);
* zip bombs: the ratio of bytes written to compressed bytes consumed is checked continuously
  while streaming (``archive_bomb``), plus absolute caps on total bytes, per-file bytes and entry
  count (``archive_too_large``);
* files are created with ``O_CREAT|O_EXCL|O_NOFOLLOW`` below a fresh destination directory, so a
  duplicate entry can never overwrite or follow anything.

``extract_archive`` runs in-process; ``validate.sandbox.unpack_sandboxed`` runs it in a separate,
resource-limited child process (that is what the pipeline uses).
"""

from __future__ import annotations

import os
import stat
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

import libarchive
import libarchive.exception

ALLOWED_FORMAT_PREFIXES = ("zip", "posix ustar", "gnu tar", "posix pax", "tar", "restricted pax", "rar")
ALLOWED_FILTERS = {"none", "gzip", "zstd"}
IGNORED_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}
IGNORED_DIRS = {"__MACOSX"}


@dataclass(frozen=True, slots=True)
class UnpackLimits:
    max_total_bytes: int = 200 * 1024**3  # absolute cap on extracted bytes (workspace quota)
    max_file_bytes: int = 64 * 1024**3
    max_entries: int = 200_000
    max_ratio: float = 100.0  # bytes written / compressed bytes read
    ratio_floor_bytes: int = 1024**3  # ratio is only enforced once this much has been written
    max_path_len: int = 1024
    max_depth: int = 32

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> UnpackLimits:
        return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})


@dataclass(slots=True)
class UnpackProblem:
    code: str  # ValidationIssue code
    message: str
    path: str | None = None
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class UnpackResult:
    ok: bool
    files: int = 0
    dirs: int = 0
    bytes_written: int = 0
    format_name: str | None = None
    filters: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    problem: UnpackProblem | None = None

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> UnpackResult:
        problem = data.get("problem")
        return cls(
            ok=bool(data["ok"]),
            files=int(data.get("files", 0)),
            dirs=int(data.get("dirs", 0)),
            bytes_written=int(data.get("bytes_written", 0)),
            format_name=data.get("format_name"),
            filters=list(data.get("filters", [])),
            skipped=list(data.get("skipped", [])),
            problem=UnpackProblem(**problem) if problem else None,
        )


class _AbortError(Exception):
    def __init__(self, problem: UnpackProblem) -> None:
        super().__init__(problem.message)
        self.problem = problem


def sanitize_member_path(raw: str, limits: UnpackLimits) -> PurePosixPath | None:
    """Return a safe relative path for an archive member, ``None`` for entries to skip.

    Raises ``_AbortError`` (archive_unsafe_path) for anything that could escape the destination.
    """
    if not raw:
        raise _AbortError(UnpackProblem("archive_unsafe_path", "Empty member name", path=raw))
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in raw):
        raise _AbortError(
            UnpackProblem("archive_unsafe_path", "Control character in member name", path=repr(raw))
        )
    name = unicodedata.normalize("NFC", raw.replace("\\", "/"))
    if len(name) > limits.max_path_len:
        raise _AbortError(UnpackProblem("archive_unsafe_path", "Member name too long", path=name[:200]))
    if name.startswith("/") or (len(name) >= 2 and name[1] == ":"):
        raise _AbortError(UnpackProblem("archive_unsafe_path", "Absolute member path", path=name))
    parts = [p for p in name.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise _AbortError(
            UnpackProblem("archive_unsafe_path", "Parent-directory component in member path", path=name)
        )
    if not parts:
        return None
    if len(parts) > limits.max_depth:
        raise _AbortError(UnpackProblem("archive_unsafe_path", "Member path too deep", path=name))
    if any(p in IGNORED_DIRS for p in parts) or parts[-1] in IGNORED_NAMES or parts[-1].startswith("._"):
        return None
    return PurePosixPath(*parts)


def _text(v: object) -> str:
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="replace")
    return "" if v is None else str(v)


def _check_format(archive: Any, result: UnpackResult) -> None:
    fmt = _text(archive.format_name).lower()
    filters = [_text(f).lower() for f in archive.filter_names]
    result.format_name = fmt
    result.filters = filters
    if not fmt.startswith(ALLOWED_FORMAT_PREFIXES):
        raise _AbortError(
            UnpackProblem(
                "archive_corrupt",
                f"Archive format not allowed: {fmt}",
                params={"reason": "format_not_allowed"},
            )
        )
    bad = [f for f in filters if f not in ALLOWED_FILTERS]
    if bad:
        raise _AbortError(
            UnpackProblem(
                "archive_corrupt",
                f"Compression filter not allowed: {bad}",
                params={"reason": "filter_not_allowed"},
            )
        )


def _ensure_dir(dest: Path, rel: PurePosixPath) -> Path:
    cur = dest
    for part in rel.parts:
        cur = cur / part
        try:
            st = os.lstat(cur)
        except FileNotFoundError:
            os.mkdir(cur, 0o755)
            continue
        if not stat.S_ISDIR(st.st_mode):
            raise _AbortError(
                UnpackProblem("archive_unsafe_path", "Path component is not a directory", path=str(rel))
            )
    return cur


def extract_archive(archive_path: Path, dest: Path, limits: UnpackLimits) -> UnpackResult:
    """Extract ``archive_path`` into the empty directory ``dest``. Never raises for archive content."""
    result = UnpackResult(ok=False)
    dest.mkdir(parents=True, exist_ok=True)
    if any(dest.iterdir()):
        raise ValueError(f"destination {dest} is not empty")
    dest = dest.resolve()
    seen: set[str] = set()
    entries = 0
    try:
        with libarchive.file_reader(str(archive_path)) as archive:
            for entry in archive:
                if entries == 0:
                    _check_format(archive, result)
                entries += 1
                if entries > limits.max_entries:
                    raise _AbortError(
                        UnpackProblem(
                            "archive_too_large",
                            "Too many archive entries",
                            params={"max_entries": limits.max_entries},
                        )
                    )
                raw = entry.pathname or ""
                if entry.issym or entry.islnk:
                    raise _AbortError(
                        UnpackProblem(
                            "archive_symlink",
                            "Archive contains a link",
                            path=raw,
                            params={"target": str(entry.linkpath or "")[:200]},
                        )
                    )
                if not (entry.isdir or entry.isreg):
                    raise _AbortError(
                        UnpackProblem("archive_unsafe_path", "Special file in archive", path=raw)
                    )
                rel = sanitize_member_path(raw, limits)
                if rel is None:
                    result.skipped.append(raw[:200])
                    continue
                key = str(rel)
                if entry.isdir:
                    _ensure_dir(dest, rel)
                    result.dirs += 1
                    continue
                if key in seen:
                    raise _AbortError(UnpackProblem("archive_unsafe_path", "Duplicate member path", path=key))
                seen.add(key)
                parent = _ensure_dir(dest, rel.parent) if rel.parent != PurePosixPath(".") else dest
                target = parent / rel.name
                fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
                written = 0
                with os.fdopen(fd, "wb") as fh:
                    for block in entry.get_blocks():
                        written += len(block)
                        result.bytes_written += len(block)
                        if written > limits.max_file_bytes:
                            raise _AbortError(
                                UnpackProblem(
                                    "archive_too_large",
                                    "File exceeds the per-file size limit",
                                    path=key,
                                    params={"max_file_bytes": limits.max_file_bytes},
                                )
                            )
                        if result.bytes_written > limits.max_total_bytes:
                            raise _AbortError(
                                UnpackProblem(
                                    "archive_too_large",
                                    "Extracted size exceeds the limit",
                                    params={"max_total_bytes": limits.max_total_bytes},
                                )
                            )
                        consumed = max(int(archive.bytes_read), 1)
                        if (
                            result.bytes_written > limits.ratio_floor_bytes
                            and result.bytes_written / consumed > limits.max_ratio
                        ):
                            raise _AbortError(
                                UnpackProblem(
                                    "archive_bomb",
                                    "Compression ratio exceeds the limit",
                                    path=key,
                                    params={
                                        "max_ratio": limits.max_ratio,
                                        "ratio": round(result.bytes_written / consumed, 1),
                                    },
                                )
                            )
                        fh.write(block)
                result.files += 1
    except _AbortError as exc:
        result.problem = exc.problem
        return result
    except libarchive.exception.ArchiveError as exc:
        msg = str(exc)
        reason = "encrypted" if "encrypt" in msg.lower() or "passphrase" in msg.lower() else "read_error"
        result.problem = UnpackProblem(
            "archive_corrupt", f"Archive cannot be read: {msg[:300]}", params={"reason": reason}
        )
        return result
    if entries == 0:
        result.problem = UnpackProblem(
            "archive_corrupt", "Archive is empty or not an archive", params={"reason": "empty"}
        )
        return result
    result.ok = True
    return result


def detect_archive_format(path: Path) -> str | None:
    """Detect the contract ``ArchiveFormat`` from magic bytes (``None`` if unknown)."""
    with path.open("rb") as fh:
        head = fh.read(512)
    if head.startswith(b"PK\x03\x04") or head.startswith(b"PK\x05\x06"):
        return "zip"
    if head.startswith(b"Rar!\x1a\x07"):
        return "rar"
    if head.startswith(b"\x1f\x8b"):
        return "tar.gz"
    if head.startswith(b"\x28\xb5\x2f\xfd"):
        return "tar.zst"
    if len(head) >= 262 and head[257:262] == b"ustar":
        return "tar"
    return None
