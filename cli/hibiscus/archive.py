"""Upload sources: an existing archive file, or a directory presented as a *virtual* tar.

A directory is never copied to a staging file. :class:`VirtualTar` computes the exact byte layout
of a deterministic POSIX/PAX tar (sorted members, fixed owner/permissions, real mtimes) and serves
any byte range on demand, so a 30 GB dataset needs no extra disk, the archive sha256 is
reproducible across runs (=> resume after a crash or reboot), and any part can be re-read for a
retry. The bytes are identical to what :mod:`tarfile` would write for the same members
(verified in tests by extracting with :mod:`tarfile`).
"""

from __future__ import annotations

import hashlib
import io
import os
import stat
import tarfile
from bisect import bisect_right
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

BLOCK = tarfile.BLOCKSIZE  # 512
RECORD = tarfile.RECORDSIZE  # 10240
READ_CHUNK = 1024 * 1024
DEFAULT_EXCLUDES = frozenset({".cache", "__pycache__", ".DS_Store", ".git"})

ARCHIVE_SUFFIXES: dict[str, str] = {
    ".tar.zst": "tar.zst",
    ".tzst": "tar.zst",
    ".tar.gz": "tar.gz",
    ".tgz": "tar.gz",
    ".tar": "tar",
    ".zip": "zip",
    ".rar": "rar",
}


class SourceChangedError(Exception):
    """The files changed after hashing; the upload would not match its sha256."""


class Source(Protocol):
    name: str
    size: int
    archive_format: str

    def fingerprint(self) -> str: ...

    def read(self, offset: int, length: int) -> bytes: ...


def detect_archive_format(path: Path) -> str | None:
    name = path.name.lower()
    for suffix, fmt in ARCHIVE_SUFFIXES.items():
        if name.endswith(suffix):
            return fmt
    return None


def _stat_fingerprint(entries: list[tuple[str, int, int]]) -> str:
    h = hashlib.sha256()
    for rel, size, mtime_ns in entries:
        h.update(f"{rel}\0{size}\0{mtime_ns}\n".encode())
    return h.hexdigest()


class FileSource:
    """An existing archive (zip / tar / tar.gz / tar.zst / rar) uploaded byte-for-byte."""

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        fmt = detect_archive_format(self.path)
        if fmt is None:
            raise ValueError(
                f"{path.name}: unsupported archive type "
                "(use .zip, .tar, .tar.gz, .tar.zst, .rar or a directory)"
            )
        self.archive_format = fmt
        self.name = self.path.name
        st = self.path.stat()
        self.size = st.st_size
        self._mtime_ns = st.st_mtime_ns

    def fingerprint(self) -> str:
        return _stat_fingerprint([(self.name, self.size, self._mtime_ns)])

    def check_unchanged(self) -> None:
        st = self.path.stat()
        if st.st_size != self.size or st.st_mtime_ns != self._mtime_ns:
            raise SourceChangedError(f"{self.path} changed during upload")

    def read(self, offset: int, length: int) -> bytes:
        with self.path.open("rb") as fh:
            fh.seek(offset)
            data = fh.read(length)
        if len(data) != length:
            raise SourceChangedError(f"{self.path}: short read at {offset}")
        return data


@dataclass(frozen=True)
class _Segment:
    offset: int
    length: int
    data: bytes | None = None  # header / padding bytes
    path: Path | None = None  # file content
    file_size: int = 0
    mtime_ns: int = 0


class VirtualTar:
    """Deterministic tar of ``root`` (top-level directory ``<root.name>/``), random access."""

    archive_format = "tar"

    def __init__(self, root: Path, *, excludes: frozenset[str] = DEFAULT_EXCLUDES) -> None:
        self.root = root.resolve()
        if not self.root.is_dir():
            raise NotADirectoryError(str(root))
        self.name = f"{self.root.name}.tar"
        self.excludes = excludes
        self._segments: list[_Segment] = []
        self._starts: list[int] = []
        self._entries: list[tuple[str, int, int]] = []
        self._build()
        self.size = self._segments[-1].offset + self._segments[-1].length if self._segments else 0

    # ------------------------------------------------------------------ layout
    def _walk(self) -> Iterator[tuple[str, Path, os.stat_result]]:
        """Yield (arcname, path, stat) in deterministic order (dirs before their contents)."""
        top = self.root.name

        def rec(directory: Path, arc: str) -> Iterator[tuple[str, Path, os.stat_result]]:
            names = sorted(os.listdir(directory), key=lambda n: n.encode("utf-8", "surrogateescape"))
            for name in names:
                if name in self.excludes:
                    continue
                p = directory / name
                child_arc = f"{arc}/{name}"
                lst = p.lstat()
                if stat.S_ISLNK(lst.st_mode):
                    try:
                        st = p.stat()
                    except FileNotFoundError as exc:
                        raise ValueError(f"broken symlink: {p}") from exc
                    if stat.S_ISDIR(st.st_mode):
                        raise ValueError(f"symlinked directories are not supported: {p}")
                    lst = st  # dereference file symlinks: the server rejects links in archives
                if stat.S_ISDIR(lst.st_mode):
                    yield child_arc, p, lst
                    yield from rec(p, child_arc)
                elif stat.S_ISREG(lst.st_mode):
                    yield child_arc, p, lst
                # sockets, fifos, devices are skipped

        yield top, self.root, self.root.stat()
        yield from rec(self.root, top)

    @staticmethod
    def _tarinfo(arcname: str, st: os.stat_result) -> tarfile.TarInfo:
        ti = tarfile.TarInfo(arcname)
        ti.mtime = int(st.st_mtime)
        ti.uid = ti.gid = 0
        ti.uname = ti.gname = ""
        if stat.S_ISDIR(st.st_mode):
            ti.type = tarfile.DIRTYPE
            ti.mode = 0o755
            ti.size = 0
        else:
            ti.type = tarfile.REGTYPE
            ti.mode = 0o755 if st.st_mode & 0o111 else 0o644
            ti.size = st.st_size
        return ti

    def _build(self) -> None:
        offset = 0
        segs: list[_Segment] = []
        for arcname, path, st in self._walk():
            ti = self._tarinfo(arcname, st)
            header = ti.tobuf(tarfile.PAX_FORMAT, "utf-8", "surrogateescape")
            segs.append(_Segment(offset, len(header), data=header))
            offset += len(header)
            if ti.type == tarfile.REGTYPE:
                rel = arcname
                self._entries.append((rel, st.st_size, st.st_mtime_ns))
                if st.st_size:
                    segs.append(
                        _Segment(offset, st.st_size, path=path, file_size=st.st_size, mtime_ns=st.st_mtime_ns)
                    )
                    offset += st.st_size
                    pad = (-st.st_size) % BLOCK
                    if pad:
                        segs.append(_Segment(offset, pad, data=b"\0" * pad))
                        offset += pad
            else:
                self._entries.append((arcname + "/", 0, 0))
        # end-of-archive: two zero blocks, then pad to a full record (as tarfile.close() does)
        end = 2 * BLOCK
        total = offset + end
        rem = total % RECORD
        if rem:
            end += RECORD - rem
        segs.append(_Segment(offset, end, data=b"\0" * end))
        self._segments = segs
        self._starts = [s.offset for s in segs]

    # ------------------------------------------------------------------ API
    @property
    def file_count(self) -> int:
        return sum(1 for rel, _, _ in self._entries if not rel.endswith("/"))

    def fingerprint(self) -> str:
        return _stat_fingerprint(self._entries)

    def check_unchanged(self) -> None:
        for seg in self._segments:
            if seg.path is not None:
                st = seg.path.stat()
                if st.st_size != seg.file_size or st.st_mtime_ns != seg.mtime_ns:
                    raise SourceChangedError(f"{seg.path} changed during upload")

    def read(self, offset: int, length: int) -> bytes:
        if offset < 0 or offset + length > self.size:
            raise ValueError("range outside archive")
        out = io.BytesIO()
        i = bisect_right(self._starts, offset) - 1
        pos = offset
        end = offset + length
        while pos < end:
            seg = self._segments[i]
            start_in = pos - seg.offset
            take = min(seg.length - start_in, end - pos)
            if seg.data is not None:
                out.write(seg.data[start_in : start_in + take])
            else:
                if seg.path is None:  # pragma: no cover - layout invariant
                    raise RuntimeError("segment without data or path")
                st = seg.path.stat()
                if st.st_size != seg.file_size or st.st_mtime_ns != seg.mtime_ns:
                    raise SourceChangedError(f"{seg.path} changed during upload")
                with seg.path.open("rb") as fh:
                    fh.seek(start_in)
                    chunk = fh.read(take)
                if len(chunk) != take:
                    raise SourceChangedError(f"{seg.path}: short read")
                out.write(chunk)
            pos += take
            i += 1
        return out.getvalue()


def iter_ranges(size: int, part_size: int) -> Iterator[tuple[int, int, int]]:
    """Yield (part_number, offset, length) for a file of ``size`` bytes."""
    n = 1
    for off in range(0, size, part_size):
        yield n, off, min(part_size, size - off)
        n += 1


def part_count(size: int, part_size: int) -> int:
    return -(-size // part_size)


def hash_source(
    src: Source, part_size: int, progress: Callable[[int], None] | None = None
) -> tuple[str, list[str]]:
    """Return (whole sha256, [per-part sha256]) streaming ``src`` once in READ_CHUNK pieces."""
    whole = hashlib.sha256()
    parts: list[str] = []
    for _n, off, length in iter_ranges(src.size, part_size):
        ph = hashlib.sha256()
        pos = off
        while pos < off + length:
            take = min(READ_CHUNK * 8, off + length - pos)
            chunk = src.read(pos, take)
            whole.update(chunk)
            ph.update(chunk)
            pos += take
            if progress:
                progress(take)
        parts.append(ph.hexdigest())
    return whole.hexdigest(), parts


def make_source(path: Path, excludes: frozenset[str] = DEFAULT_EXCLUDES) -> FileSource | VirtualTar:
    if path.is_dir():
        return VirtualTar(path, excludes=excludes)
    if path.is_file():
        return FileSource(path)
    raise FileNotFoundError(str(path))
