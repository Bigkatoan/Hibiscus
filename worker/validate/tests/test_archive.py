"""Adversarial and format tests for the sandboxed libarchive unpacker."""

from __future__ import annotations

import io
import os
import stat
import tarfile
import zipfile
from pathlib import Path

import libarchive
import pytest

from validate.archive import UnpackLimits, detect_archive_format, extract_archive, sanitize_member_path
from validate.sandbox import unpack_sandboxed

LIMITS = UnpackLimits()


def _outside_untouched(tmp_path: Path) -> None:
    assert not (tmp_path / "evil.txt").exists()
    assert not (tmp_path.parent / "evil.txt").exists()


def _tar(path: Path, members: list[tuple[tarfile.TarInfo, bytes | None]], mode: str = "w") -> Path:
    with tarfile.open(path, mode) as tf:  # type: ignore[call-overload]  # mode literal union
        for info, data in members:
            tf.addfile(info, io.BytesIO(data) if data is not None else None)
    return path


def _reg(name: str, data: bytes) -> tuple[tarfile.TarInfo, bytes]:
    ti = tarfile.TarInfo(name)
    ti.size = len(data)
    ti.mode = 0o644
    return ti, data


# --------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "name",
    ["../evil.txt", "a/../../evil.txt", "/etc/evil.txt", "C:/evil.txt", "..\\evil.txt", "a/\x00b", "a/\x1bb"],
)
def test_sanitize_rejects_escape(name: str) -> None:
    from validate.archive import _AbortError

    with pytest.raises(_AbortError) as ei:
        sanitize_member_path(name, LIMITS)
    assert ei.value.problem.code == "archive_unsafe_path"


def test_sanitize_normalises_and_skips_junk() -> None:
    assert str(sanitize_member_path("./a//b/./c.txt", LIMITS)) == "a/b/c.txt"
    assert str(sanitize_member_path("a\\b\\c.txt", LIMITS)) == "a/b/c.txt"
    assert sanitize_member_path("__MACOSX/a/._b", LIMITS) is None
    assert sanitize_member_path("ds/.DS_Store", LIMITS) is None
    assert sanitize_member_path("./", LIMITS) is None


def test_zip_parent_traversal_rejected(tmp_path: Path) -> None:
    arc = tmp_path / "t.zip"
    with zipfile.ZipFile(arc, "w") as zf:
        zf.writestr("ok.txt", b"fine")
        zf.writestr(zipfile.ZipInfo("../evil.txt"), b"pwned")
    dest = tmp_path / "out" / "dest"
    res = unpack_sandboxed(arc, dest, LIMITS)
    assert not res.ok
    assert res.problem is not None and res.problem.code == "archive_unsafe_path"
    _outside_untouched(tmp_path / "out")
    assert not (tmp_path / "out" / "evil.txt").exists()


def test_tar_absolute_path_rejected(tmp_path: Path) -> None:
    arc = _tar(tmp_path / "t.tar", [_reg(str(tmp_path / "evil.txt"), b"pwned")])
    res = extract_archive(arc, tmp_path / "dest", LIMITS)
    assert not res.ok and res.problem is not None
    assert res.problem.code == "archive_unsafe_path"
    _outside_untouched(tmp_path)


def test_tar_symlink_rejected(tmp_path: Path) -> None:
    link = tarfile.TarInfo("ds/meta")
    link.type = tarfile.SYMTYPE
    link.linkname = "/etc"
    arc = _tar(tmp_path / "t.tar", [(link, None), _reg("ds/meta/info.json", b"{}")])
    res = unpack_sandboxed(arc, tmp_path / "out" / "dest", LIMITS)
    assert not res.ok and res.problem is not None
    assert res.problem.code == "archive_symlink"
    assert res.problem.params["target"] == "/etc"
    assert not (tmp_path / "out" / "dest" / "ds" / "meta").exists()


def test_tar_hardlink_rejected(tmp_path: Path) -> None:
    hl = tarfile.TarInfo("ds/passwd")
    hl.type = tarfile.LNKTYPE
    hl.linkname = "/etc/passwd"
    arc = _tar(tmp_path / "t.tar", [_reg("ds/a.txt", b"x"), (hl, None)])
    res = extract_archive(arc, tmp_path / "dest", LIMITS)
    assert not res.ok and res.problem is not None
    assert res.problem.code == "archive_symlink"


def test_zip_symlink_rejected(tmp_path: Path) -> None:
    arc = tmp_path / "t.zip"
    zi = zipfile.ZipInfo("ds/link")
    zi.create_system = 3
    zi.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(arc, "w") as zf:
        zf.writestr(zi, "/etc/passwd")
    res = extract_archive(arc, tmp_path / "dest", LIMITS)
    assert not res.ok and res.problem is not None
    assert res.problem.code == "archive_symlink"
    assert not os.path.lexists(tmp_path / "dest" / "ds" / "link")


def test_tar_device_and_fifo_rejected(tmp_path: Path) -> None:
    for typ in (tarfile.CHRTYPE, tarfile.FIFOTYPE):
        dev = tarfile.TarInfo("ds/dev")
        dev.type = typ
        arc = _tar(tmp_path / f"t{typ!r}.tar", [(dev, None)])
        res = extract_archive(arc, tmp_path / f"dest{ord(typ)}", LIMITS)
        assert not res.ok and res.problem is not None
        assert res.problem.code == "archive_unsafe_path"


def test_duplicate_member_rejected(tmp_path: Path) -> None:
    arc = _tar(tmp_path / "t.tar", [_reg("ds/a.txt", b"one"), _reg("ds/a.txt", b"two")])
    res = extract_archive(arc, tmp_path / "dest", LIMITS)
    assert not res.ok and res.problem is not None
    assert res.problem.code == "archive_unsafe_path"
    assert (tmp_path / "dest" / "ds" / "a.txt").read_bytes() == b"one"


def test_zip_bomb_stopped_by_ratio(tmp_path: Path) -> None:
    arc = tmp_path / "bomb.zip"
    chunk = b"\0" * (1024 * 1024)
    with zipfile.ZipFile(arc, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        with zf.open("ds/zeros.bin", "w", force_zip64=True) as fh:
            for _ in range(256):  # 256 MiB of zeros -> ~250 KiB compressed
                fh.write(chunk)
    assert arc.stat().st_size < 2 * 1024 * 1024
    limits = UnpackLimits(max_ratio=100.0, ratio_floor_bytes=8 * 1024 * 1024)
    dest = tmp_path / "out" / "dest"
    res = unpack_sandboxed(arc, dest, limits)
    assert not res.ok and res.problem is not None
    assert res.problem.code == "archive_bomb"
    assert res.problem.params["ratio"] > 100
    # Stopped early: far less than the 256 MiB payload hit the disk.
    written = sum(p.stat().st_size for p in dest.rglob("*") if p.is_file())
    assert written < 64 * 1024 * 1024


def test_size_caps(tmp_path: Path) -> None:
    arc = _tar(tmp_path / "t.tar", [_reg("ds/a.bin", b"x" * 5000), _reg("ds/b.bin", b"y" * 5000)])
    res = extract_archive(arc, tmp_path / "d1", UnpackLimits(max_file_bytes=4096))
    assert res.problem is not None and res.problem.code == "archive_too_large"
    res = extract_archive(arc, tmp_path / "d2", UnpackLimits(max_total_bytes=8000))
    assert res.problem is not None and res.problem.code == "archive_too_large"
    res = extract_archive(arc, tmp_path / "d3", UnpackLimits(max_entries=1))
    assert res.problem is not None and res.problem.code == "archive_too_large"


def test_corrupt_and_empty_inputs(tmp_path: Path) -> None:
    junk = tmp_path / "junk.zip"
    junk.write_bytes(os.urandom(4096))
    res = unpack_sandboxed(junk, tmp_path / "o1" / "d", LIMITS)
    assert not res.ok and res.problem is not None and res.problem.code == "archive_corrupt"

    good = tmp_path / "g.zip"
    with zipfile.ZipFile(good, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("ds/big.bin", os.urandom(200_000))
    truncated = tmp_path / "trunc.zip"
    truncated.write_bytes(good.read_bytes()[:100_000])
    res = unpack_sandboxed(truncated, tmp_path / "o2" / "d", LIMITS)
    assert not res.ok and res.problem is not None and res.problem.code == "archive_corrupt"

    empty = tmp_path / "e.tar"
    _tar(empty, [])
    res = extract_archive(empty, tmp_path / "d3", LIMITS)
    assert not res.ok and res.problem is not None and res.problem.code == "archive_corrupt"


def test_disallowed_format_rejected(tmp_path: Path) -> None:
    src = tmp_path / "f.txt"
    src.write_bytes(b"data")
    arc = tmp_path / "a.cpio"
    with libarchive.file_writer(str(arc), "cpio") as w:
        w.add_files(str(src))
    res = extract_archive(arc, tmp_path / "d", LIMITS)
    assert not res.ok and res.problem is not None
    assert res.problem.code == "archive_corrupt"
    assert res.problem.params["reason"] == "format_not_allowed"


def _write_tree_with_libarchive(arc: Path, fmt: str, filt: str | None, base: Path) -> None:
    cwd = os.getcwd()
    os.chdir(base)
    try:
        with libarchive.file_writer(str(arc), fmt, filt) as w:
            w.add_files("ds")
    finally:
        os.chdir(cwd)


@pytest.mark.parametrize(
    ("fmt", "filt", "expected"),
    [("zip", None, "zip"), ("pax", None, "tar"), ("pax", "gzip", "tar.gz"), ("pax", "zstd", "tar.zst")],
)
def test_supported_formats_round_trip(tmp_path: Path, fmt: str, filt: str | None, expected: str) -> None:
    base = tmp_path / "src"
    (base / "ds" / "meta").mkdir(parents=True)
    (base / "ds" / "meta" / "info.json").write_text('{"a": 1}')
    (base / "ds" / "data.bin").write_bytes(os.urandom(10000))
    arc = tmp_path / f"a.{expected}"
    _write_tree_with_libarchive(arc, fmt, filt, base)
    assert detect_archive_format(arc) == expected
    res = unpack_sandboxed(arc, tmp_path / "o" / "d", LIMITS)
    assert res.ok, res.problem
    out = tmp_path / "o" / "d" / "ds"
    assert (out / "meta" / "info.json").read_text() == '{"a": 1}'
    assert (out / "data.bin").read_bytes() == (base / "ds" / "data.bin").read_bytes()
    assert res.files == 2


def test_detect_rar_magic() -> None:
    golden = Path("~/lelab/Picknplace_20261114_221710.rar")
    if not golden.exists():
        pytest.skip("golden archive not present on this machine")
    assert detect_archive_format(golden) == "rar"


def test_destination_must_be_empty(tmp_path: Path) -> None:
    arc = _tar(tmp_path / "t.tar", [_reg("ds/a.txt", b"x")])
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "x").write_text("x")
    with pytest.raises(ValueError, match="not empty"):
        extract_archive(arc, tmp_path / "d", LIMITS)
