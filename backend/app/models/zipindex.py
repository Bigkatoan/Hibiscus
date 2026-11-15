"""Read single members of a zip stored in S3 through HTTP Range requests (getModelFile).

Only the central directory (tail of the archive) and the requested member are fetched. Stored
members (``*.safetensors``, ``*.onnx``, ``*.png`` per bundle.md §1) are served byte-ranged
directly; deflated members are decompressed on the fly. Zip64 is supported.
"""

from __future__ import annotations

import struct
import zlib
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

EOCD_SIG = b"PK\x05\x06"
EOCD64_LOC_SIG = b"PK\x06\x07"
EOCD64_SIG = b"PK\x06\x06"
CDH_SIG = b"PK\x01\x02"
LFH_SIG = b"PK\x03\x04"

Fetch = Callable[[int, int], Awaitable[bytes]]  # inclusive byte range


class ZipError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Member:
    name: str
    method: int  # 0 stored, 8 deflate
    compressed_size: int
    size: int
    header_offset: int
    crc: int


def _zip64_extra(extra: bytes, size: int, csize: int, offset: int) -> tuple[int, int, int]:
    i = 0
    while i + 4 <= len(extra):
        hid, hlen = struct.unpack_from("<HH", extra, i)
        body = extra[i + 4 : i + 4 + hlen]
        if hid == 0x0001:
            j = 0
            if size == 0xFFFFFFFF:
                size = struct.unpack_from("<Q", body, j)[0]
                j += 8
            if csize == 0xFFFFFFFF:
                csize = struct.unpack_from("<Q", body, j)[0]
                j += 8
            if offset == 0xFFFFFFFF:
                offset = struct.unpack_from("<Q", body, j)[0]
        i += 4 + hlen
    return size, csize, offset


async def read_index(fetch: Fetch, total_size: int) -> dict[str, Member]:
    tail_len = min(total_size, 65536 + 22)
    tail = await fetch(total_size - tail_len, total_size - 1)
    pos = tail.rfind(EOCD_SIG)
    if pos < 0:
        raise ZipError("end of central directory not found")
    _, _, _, _, n_total, cd_size, cd_off, _ = struct.unpack_from("<4sHHHHIIH", tail, pos)
    if cd_off == 0xFFFFFFFF or n_total == 0xFFFF or cd_size == 0xFFFFFFFF:
        loc = tail.rfind(EOCD64_LOC_SIG, 0, pos)
        if loc < 0:
            raise ZipError("zip64 locator missing")
        (eocd64_off,) = struct.unpack_from("<Q", tail, loc + 8)
        rec = await fetch(eocd64_off, eocd64_off + 55)
        if rec[:4] != EOCD64_SIG:
            raise ZipError("bad zip64 record")
        n_total, cd_size, cd_off = struct.unpack_from("<QQQ", rec, 32)
    cd = await fetch(cd_off, cd_off + cd_size - 1)
    members: dict[str, Member] = {}
    i = 0
    for _ in range(n_total):
        if cd[i : i + 4] != CDH_SIG:
            raise ZipError("bad central directory entry")
        (method, crc, csize, size, nlen, elen, clen, off) = (
            struct.unpack_from("<H", cd, i + 10)[0],
            struct.unpack_from("<I", cd, i + 16)[0],
            struct.unpack_from("<I", cd, i + 20)[0],
            struct.unpack_from("<I", cd, i + 24)[0],
            struct.unpack_from("<H", cd, i + 28)[0],
            struct.unpack_from("<H", cd, i + 30)[0],
            struct.unpack_from("<H", cd, i + 32)[0],
            struct.unpack_from("<I", cd, i + 42)[0],
        )
        name = cd[i + 46 : i + 46 + nlen].decode("utf-8")
        extra = cd[i + 46 + nlen : i + 46 + nlen + elen]
        size, csize, off = _zip64_extra(extra, size, csize, off)
        members[name] = Member(name, method, csize, size, off, crc)
        i += 46 + nlen + elen + clen
    return members


async def data_offset(fetch: Fetch, m: Member) -> int:
    hdr = await fetch(m.header_offset, m.header_offset + 29)
    if hdr[:4] != LFH_SIG:
        raise ZipError("bad local header")
    nlen, elen = struct.unpack_from("<HH", hdr, 26)
    return int(m.header_offset) + 30 + int(nlen) + int(elen)


async def stream_member(
    fetch: Fetch, m: Member, start: int, end: int, chunk: int = 1 << 20
) -> AsyncIterator[bytes]:
    """Yield bytes ``[start, end]`` (inclusive) of the *uncompressed* member."""
    base = await data_offset(fetch, m)
    if m.method == 0:
        pos = start
        while pos <= end:
            hi = min(end, pos + chunk - 1)
            yield await fetch(base + pos, base + hi)
            pos = hi + 1
        return
    if m.method != 8:
        raise ZipError(f"unsupported compression {m.method}")
    d = zlib.decompressobj(-15)
    produced = 0
    cpos = 0
    while cpos < m.compressed_size and produced <= end:
        hi = min(m.compressed_size - 1, cpos + chunk - 1)
        raw = d.decompress(await fetch(base + cpos, base + hi))
        cpos = hi + 1
        lo_cut = max(start - produced, 0)
        hi_cut = min(end - produced + 1, len(raw))
        if hi_cut > lo_cut:
            yield raw[lo_cut:hi_cut]
        produced += len(raw)
