from __future__ import annotations

import hashlib
import io
import os
import tarfile
from pathlib import Path

import pytest

from hibiscus.archive import (
    FileSource,
    SourceChangedError,
    VirtualTar,
    detect_archive_format,
    hash_source,
    iter_ranges,
    make_source,
    part_count,
)


def _tree(root: Path) -> Path:
    ds = root / "my_dataset"
    (ds / "meta" / "episodes" / "chunk-000").mkdir(parents=True)
    (ds / "data" / "chunk-000").mkdir(parents=True)
    (ds / "meta" / "info.json").write_text('{"codebase_version": "v3.0"}')
    (ds / "data" / "chunk-000" / "file-000.parquet").write_bytes(os.urandom(70_001))
    (ds / "meta" / "episodes" / "chunk-000" / "file-000.parquet").write_bytes(b"")  # empty file
    long_name = "x" * 150 + ".bin"  # > 100 chars => PAX header
    (ds / long_name).write_bytes(b"long")
    (ds / "tiếng_việt.txt").write_text("xin chào")  # non-ASCII name => PAX header
    script = ds / "run.sh"
    script.write_text("#!/bin/sh\n")
    script.chmod(0o755)
    (ds / ".cache").mkdir()
    (ds / ".cache" / "junk").write_text("excluded")
    (ds / "link.json").symlink_to(ds / "meta" / "info.json")
    return ds


def _full(vt: VirtualTar) -> bytes:
    return vt.read(0, vt.size)


def test_virtual_tar_extracts_with_tarfile(tmp_path: Path) -> None:
    ds = _tree(tmp_path)
    vt = VirtualTar(ds)
    blob = _full(vt)
    assert len(blob) == vt.size
    assert vt.size % tarfile.RECORDSIZE == 0
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:") as tf:
        names = tf.getnames()
        members = {m.name: m for m in tf.getmembers()}
        out = tmp_path / "out"
        tf.extractall(out, filter="data")
    assert names[0] == "my_dataset"
    assert "my_dataset/.cache" not in names and "my_dataset/.cache/junk" not in names
    for rel in ("data/chunk-000/file-000.parquet", "meta/info.json", "x" * 150 + ".bin", "tiếng_việt.txt"):
        assert (out / "my_dataset" / rel).read_bytes() == (ds / rel).read_bytes()
    # file symlink dereferenced into a regular file (server rejects links)
    assert members["my_dataset/link.json"].isfile()
    assert (out / "my_dataset" / "link.json").read_bytes() == (ds / "meta" / "info.json").read_bytes()
    assert members["my_dataset/run.sh"].mode == 0o755
    assert members["my_dataset/meta/info.json"].mode == 0o644
    assert members["my_dataset/meta/info.json"].uid == 0
    assert vt.file_count == 7


def test_virtual_tar_matches_tarfile_bytes(tmp_path: Path) -> None:
    """Our layout is byte-identical to tarfile writing the same TarInfo members."""
    ds = _tree(tmp_path)
    (ds / "link.json").unlink()
    vt = VirtualTar(ds)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tf:
        for arc, path, st in vt._walk():
            ti = VirtualTar._tarinfo(arc, st)
            if ti.isfile():
                with path.open("rb") as fh:
                    tf.addfile(ti, fh)
            else:
                tf.addfile(ti)
    assert _full(vt) == buf.getvalue()


def test_virtual_tar_is_deterministic_and_random_access(tmp_path: Path) -> None:
    ds = _tree(tmp_path)
    a, b = VirtualTar(ds), VirtualTar(ds)
    assert a.size == b.size and a.fingerprint() == b.fingerprint()
    full = _full(a)
    assert hashlib.sha256(full).hexdigest() == hashlib.sha256(_full(b)).hexdigest()
    # arbitrary ranges straddling header/data/padding boundaries
    for off, ln in [(0, 1), (511, 2), (1000, 70_000), (a.size - 1, 1), (12345, 9999)]:
        assert a.read(off, ln) == full[off : off + ln]
    with pytest.raises(ValueError):
        a.read(a.size - 1, 2)


def test_hash_source_parts_match_ranges(tmp_path: Path) -> None:
    ds = _tree(tmp_path)
    vt = VirtualTar(ds)
    full = _full(vt)
    part = 20_000
    whole, parts = hash_source(vt, part)
    assert whole == hashlib.sha256(full).hexdigest()
    assert len(parts) == part_count(vt.size, part)
    for n, off, ln in iter_ranges(vt.size, part):
        assert parts[n - 1] == hashlib.sha256(full[off : off + ln]).hexdigest()


def test_change_detection(tmp_path: Path) -> None:
    ds = _tree(tmp_path)
    vt = VirtualTar(ds)
    fp = vt.fingerprint()
    target = ds / "data" / "chunk-000" / "file-000.parquet"
    target.write_bytes(os.urandom(70_001))
    os.utime(target, ns=(1, 1))
    with pytest.raises(SourceChangedError):
        vt.check_unchanged()
    with pytest.raises(SourceChangedError):
        vt.read(0, vt.size)
    assert VirtualTar(ds).fingerprint() != fp


def test_symlinked_dir_rejected(tmp_path: Path) -> None:
    ds = _tree(tmp_path)
    (ds / "loop").symlink_to(ds)
    with pytest.raises(ValueError, match="symlinked directories"):
        VirtualTar(ds)


def test_file_source_and_formats(tmp_path: Path) -> None:
    for name, fmt in [
        ("a.rar", "rar"),
        ("b.tar.zst", "tar.zst"),
        ("c.TGZ", "tar.gz"),
        ("d.zip", "zip"),
        ("e.tar", "tar"),
        ("f.txt", None),
    ]:
        assert detect_archive_format(Path(name)) == fmt
    f = tmp_path / "x.zip"
    f.write_bytes(b"PK" + os.urandom(1000))
    src = make_source(f)
    assert isinstance(src, FileSource)
    assert src.read(0, 2) == b"PK" and src.size == 1002 and src.archive_format == "zip"
    with pytest.raises(SourceChangedError):
        src.read(1000, 10)
    bad = tmp_path / "x.txt"
    bad.write_text("nope")
    with pytest.raises(ValueError, match="unsupported archive"):
        make_source(bad)
    with pytest.raises(FileNotFoundError):
        make_source(tmp_path / "missing.zip")
