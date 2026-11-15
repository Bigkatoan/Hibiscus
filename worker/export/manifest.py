"""MANIFEST.json, zip packaging and the ``manifest_ok`` re-hash check (docs/spec/bundle.md §1, §3, §10)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

MANIFEST_NAME = "MANIFEST.json"
STORED_SUFFIXES = (".safetensors", ".onnx", ".png")
EXEC_SUFFIXES = (".sh", ".py")
_CHUNK = 1 << 20


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def iter_files(root: Path) -> list[Path]:
    """All regular files under ``root``; symlinks are rejected (spec §1: no symlinks)."""
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for name in [*dirnames, *filenames]:
            p = Path(dirpath) / name
            if p.is_symlink():
                raise ValueError(f"symlink not allowed in bundle: {p.relative_to(root)}")
        for name in filenames:
            out.append(Path(dirpath) / name)
    return out


def file_entries(bundle_dir: Path) -> list[dict[str, Any]]:
    """Every file except MANIFEST.json, sorted bytewise by POSIX path."""
    entries = []
    for p in iter_files(bundle_dir):
        rel = p.relative_to(bundle_dir).as_posix()
        if rel == MANIFEST_NAME:
            continue
        entries.append({"path": rel, "size": p.stat().st_size, "sha256": sha256_file(p)})
    entries.sort(key=lambda e: str(e["path"]).encode("utf-8"))
    return entries


def write_manifest(bundle_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    doc = dict(manifest)
    doc["files"] = file_entries(bundle_dir)
    (bundle_dir / MANIFEST_NAME).write_text(json.dumps(doc, indent=2) + "\n")
    return doc


def copy_tree_exact(src: Path, dst: Path) -> None:
    """Byte-identical copy of a checkpoint directory (no symlinks, regular files only)."""
    for p in iter_files(src):
        rel = p.relative_to(src)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, target)
        os.chmod(target, 0o644)


def _zip_mode(path: str) -> int:
    perm = 0o755 if path.endswith(EXEC_SUFFIXES) else 0o644
    return (stat.S_IFREG | perm) << 16


def zip_bundle(bundle_dir: Path, zip_path: Path, *, date_time: datetime | None = None) -> str:
    """Create ``<bundle_name>.zip`` with one top-level directory; returns its sha256."""
    name = bundle_dir.name
    ts = (date_time or datetime.now()).timetuple()[:6]
    ts = max(ts, (1980, 1, 1, 0, 0, 0))
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    files = sorted(iter_files(bundle_dir), key=lambda p: p.relative_to(bundle_dir).as_posix().encode())
    with zipfile.ZipFile(zip_path, "w", allowZip64=True) as zf:
        for p in files:
            rel = p.relative_to(bundle_dir).as_posix()
            arc = f"{name}/{rel}"
            info = zipfile.ZipInfo(arc, date_time=ts)
            info.external_attr = _zip_mode(rel)
            info.create_system = 3  # Unix, so external_attr permissions are honoured
            # Deflate without an explicit level = zlib Z_DEFAULT_COMPRESSION, i.e. level 6 (spec §1).
            stored = rel.endswith(STORED_SUFFIXES)
            info.compress_type = zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED
            with p.open("rb") as src, zf.open(info, "w", force_zip64=True) as dst:
                shutil.copyfileobj(src, dst, _CHUNK)
    return sha256_file(zip_path)


@dataclass
class ManifestCheck:
    ok: bool
    detail: str | None
    n_files: int


def _safe_member(name: str, top: str) -> bool:
    p = PurePosixPath(name)
    return not p.is_absolute() and ".." not in p.parts and p.parts[:1] == (top,)


def verify_zip(zip_path: Path, expected_name: str | None = None) -> ManifestCheck:
    """Unzip to a temp dir, re-hash every file and compare with MANIFEST.json (no extra/missing)."""
    with zipfile.ZipFile(zip_path) as zf:
        names = [i.filename for i in zf.infolist() if not i.is_dir()]
        tops = {PurePosixPath(n).parts[0] for n in names}
        if len(tops) != 1:
            return ManifestCheck(False, f"expected one top-level directory, found {sorted(tops)}", 0)
        top = next(iter(tops))
        if expected_name is not None and top != expected_name:
            return ManifestCheck(False, f"top-level directory {top!r} != {expected_name!r}", 0)
        for info in zf.infolist():
            if not _safe_member(info.filename, top):
                return ManifestCheck(False, f"unsafe path in zip: {info.filename!r}", 0)
            if stat.S_ISLNK(info.external_attr >> 16):
                return ManifestCheck(False, f"symlink in zip: {info.filename!r}", 0)
        with tempfile.TemporaryDirectory(prefix="hibiscus-verify-") as tmp:
            zf.extractall(tmp)  # members validated above
            root = Path(tmp) / top
            mpath = root / MANIFEST_NAME
            if not mpath.is_file():
                return ManifestCheck(False, "MANIFEST.json missing", 0)
            manifest = json.loads(mpath.read_text())
            if manifest.get("bundle_name") != top:
                return ManifestCheck(False, "MANIFEST.bundle_name does not match the zip directory", 0)
            listed = {str(e["path"]): e for e in manifest.get("files", [])}
            actual = {e["path"]: e for e in file_entries(root)}
            missing = sorted(set(listed) - set(actual))
            extra = sorted(set(actual) - set(listed))
            if missing or extra:
                return ManifestCheck(False, f"missing={missing[:5]} extra={extra[:5]}", len(actual))
            bad = [
                p
                for p, e in listed.items()
                if e["sha256"] != actual[p]["sha256"] or e["size"] != actual[p]["size"]
            ]
            if bad:
                return ManifestCheck(False, f"hash/size mismatch: {bad[:5]}", len(actual))
            order = [str(e["path"]) for e in manifest.get("files", [])]
            if order != sorted(order, key=lambda s: s.encode("utf-8")):
                return ManifestCheck(False, "MANIFEST.files not sorted bytewise", len(actual))
            return ManifestCheck(True, None, len(actual))
