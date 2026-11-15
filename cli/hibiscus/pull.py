"""``hibiscus pull <model> --to <dir>`` (operationIds getModel, downloadModel, listModelFiles, getModelFile).

Two modes:

* **zip** (default): ``GET /models/{id}/download`` into ``<to>/.hibiscus-partial/<id>.zip.part``,
  resuming with ``Range: bytes=<have>-`` + ``If-Range: <ETag>``; the zip's sha256 must equal
  ``Model.bundle_sha256`` (= ETag). Extracted safely (no absolute paths, ``..``, symlinks, or
  entries outside the single ``<bundle_name>/`` top-level directory).
* **files** (``--only <prefix>``, e.g. ``pretrained_model``): ``GET /models/{id}/files`` gives
  MANIFEST.json; each selected file is fetched with ``GET /models/{id}/files/{path}`` (Range resume)
  and checked against its manifest sha256 / size.

Both modes finish by verifying ``MANIFEST.json`` (docs/spec/bundle.md §3): every listed file
present with matching size and sha256 and (zip mode) no unlisted files. The bundle is assembled in
a temp dir next to the destination and renamed into place only after verification.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote

import httpx

from hibiscus.api import ApiError, HibiscusApi, is_transport_error

CHUNK = 1024 * 1024


class PullError(Exception):
    pass


@dataclass
class PullEvents:
    on_start: Callable[[int, int], None] = lambda total, have: None
    on_bytes: Callable[[int], None] = lambda n: None
    on_info: Callable[[str], None] = lambda msg: None


@dataclass
class PullResult:
    bundle_dir: Path
    bundle_name: str
    files_verified: int
    bytes_downloaded: int
    resumed_from: int = 0
    skipped: bool = False
    problems: list[str] = field(default_factory=list)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def _safe_rel(name: str) -> PurePosixPath:
    """Reject absolute, parent-escaping, drive-letter or backslash paths from the server."""
    p = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or "\0" in name
        or p.is_absolute()
        or not p.parts
        or ".." in p.parts
        or ":" in p.parts[0]
    ):
        raise PullError(f"unsafe path in bundle: {name!r}")
    return p


def verify_manifest(
    bundle_dir: Path, *, strict_extra: bool = True, only: str | None = None
) -> tuple[int, list[str]]:
    """Check files against ``MANIFEST.json``; returns (files checked, problems)."""
    manifest_path = bundle_dir / "MANIFEST.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return 0, ["MANIFEST.json missing"]
    except ValueError as exc:
        return 0, [f"MANIFEST.json invalid: {exc}"]
    problems: list[str] = []
    listed: set[str] = set()
    checked = 0
    for entry in manifest.get("files", []):
        rel = str(entry["path"])
        listed.add(rel)
        if only is not None and not _selected(rel, only):
            continue
        _safe_rel(rel)
        p = bundle_dir / rel
        if not p.is_file():
            problems.append(f"missing: {rel}")
            continue
        if p.stat().st_size != int(entry["size"]):
            problems.append(f"size mismatch: {rel}")
            continue
        if sha256_file(p) != entry["sha256"]:
            problems.append(f"sha256 mismatch: {rel}")
            continue
        checked += 1
    if strict_extra:
        for p in sorted(bundle_dir.rglob("*")):
            if p.is_file():
                rel = p.relative_to(bundle_dir).as_posix()
                if rel != "MANIFEST.json" and rel not in listed:
                    problems.append(f"not in manifest: {rel}")
    return checked, problems


def _selected(rel: str, only: str) -> bool:
    only = only.strip("/")
    return rel == only or rel.startswith(only + "/")


class Puller:
    def __init__(self, api: HibiscusApi, events: PullEvents | None = None) -> None:
        self.api = api
        self.events = events or PullEvents()

    # ------------------------------------------------------------------ download helpers
    def _download(
        self, url: str, dest: Path, *, etag: str | None, expected_size: int | None
    ) -> tuple[int, int]:
        """Range-resumable GET into ``dest``; returns (bytes fetched now, resumed offset)."""
        attempt = 0
        fetched = 0
        first_offset = dest.stat().st_size if dest.exists() else 0
        while True:
            have = dest.stat().st_size if dest.exists() else 0
            if expected_size is not None and have == expected_size:
                return fetched, first_offset
            if expected_size is not None and have > expected_size:
                dest.unlink()
                have = 0
            headers: dict[str, str] = {}
            etag_file = dest.with_name(dest.name + ".etag")
            if have:
                headers["Range"] = f"bytes={have}-"
                known = etag_file.read_text(encoding="utf-8").strip() if etag_file.exists() else etag
                if known:
                    headers["If-Range"] = known
            try:
                with self.api.stream(
                    "GET", url, headers=headers, timeout=httpx.Timeout(300.0, connect=15.0)
                ) as r:
                    if r.status_code == 416 and have:
                        dest.unlink()  # local partial is bigger/stale: start over
                        continue
                    if r.status_code not in (200, 206):
                        r.read()
                        err = ApiError.from_http(r.status_code, r.content, r.headers)
                        if err.retryable and attempt + 1 < self.api.backoff.attempts:
                            self.api.backoff.sleep(self.api.backoff.delay(attempt, err.retry_after_s))
                            attempt += 1
                            continue
                        raise err
                    if r.status_code == 200 and have:
                        have = 0  # server ignored Range / ETag changed: full body follows
                    if r.status_code == 200 and r.headers.get("ETag"):
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        etag_file.write_text(r.headers["ETag"], encoding="utf-8")
                    total = expected_size
                    if total is None:
                        cl = r.headers.get("Content-Length")
                        total = (int(cl) + have) if cl and cl.isdigit() else None
                    self.events.on_start(total or 0, have)
                    mode = "ab" if have else "wb"
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with dest.open(mode) as fh:
                        for chunk in r.iter_bytes():  # no chunk_size: write as received (resume point)
                            fh.write(chunk)
                            fetched += len(chunk)
                            self.events.on_bytes(len(chunk))
                    if expected_size is None or dest.stat().st_size >= expected_size:
                        etag_file.unlink(missing_ok=True)
                        return fetched, first_offset
                    raise httpx.RemoteProtocolError("body shorter than expected")
            except ApiError:
                raise
            except Exception as exc:
                if not is_transport_error(exc) or attempt + 1 >= self.api.backoff.attempts:
                    raise
                self.events.on_info(f"download interrupted ({type(exc).__name__}); resuming")
                self.api.backoff.sleep(self.api.backoff.delay(attempt))
                attempt += 1

    # ------------------------------------------------------------------ public
    def pull(self, model_id: str, to: Path, *, only: str | None = None, force: bool = False) -> PullResult:
        model = self.api.get_model(model_id).to_dict()
        if model.get("status") != "ready":
            raise PullError(f"model is {model.get('status')}, not ready (code model_not_ready)")
        to = to.resolve()
        to.mkdir(parents=True, exist_ok=True)
        if only is not None:
            return self._pull_files(model, to, only=only, force=force)
        return self._pull_zip(model, to, force=force)

    def _existing_ok(self, final: Path, only: str | None) -> PullResult | None:
        if not (final / "MANIFEST.json").is_file():
            return None
        checked, problems = verify_manifest(final, strict_extra=only is None, only=only)
        if problems:
            return None
        return PullResult(final, final.name, checked, 0, skipped=True)

    def _pull_zip(self, model: dict[str, Any], to: Path, *, force: bool) -> PullResult:
        model_id = str(model["id"])
        expected_sha = model.get("bundle_sha256")
        size = model.get("bundle_size_bytes")
        partial_dir = to / ".hibiscus-partial"
        part = partial_dir / f"{model_id}.zip.part"
        if not force:
            try:
                bundle_name = str(self.api.list_model_files(model_id).to_dict()["bundle_name"])
                _safe_rel(bundle_name)
            except (ApiError, PullError, KeyError):
                bundle_name = ""
            if bundle_name and "/" not in bundle_name:
                done = self._existing_ok(to / bundle_name, None)
                if done:
                    return done
        fetched, resumed = self._download(
            f"/models/{model_id}/download",
            part,
            etag=f'"{expected_sha}"' if expected_sha else None,
            expected_size=int(size) if isinstance(size, int) else None,
        )
        digest = sha256_file(part)
        if expected_sha and digest != expected_sha:
            part.unlink()
            raise PullError(
                f"bundle sha256 mismatch (got {digest}, expected {expected_sha}); partial removed, retry"
            )
        bundle_name, staged = self._extract(part, to)
        checked, problems = verify_manifest(staged)
        if problems:
            shutil.rmtree(staged.parent, ignore_errors=True)
            raise PullError("MANIFEST verification failed: " + "; ".join(problems[:10]))
        final = to / bundle_name
        if not force:
            done = self._existing_ok(final, None)
            if done:
                shutil.rmtree(staged.parent, ignore_errors=True)
                part.unlink(missing_ok=True)
                return done
        self._replace(staged, final)
        shutil.rmtree(staged.parent, ignore_errors=True)
        part.unlink(missing_ok=True)
        _rmdir_quiet(partial_dir)
        return PullResult(final, bundle_name, checked, fetched, resumed_from=resumed)

    def _extract(self, zpath: Path, to: Path) -> tuple[str, Path]:
        tmp = Path(tempfile.mkdtemp(prefix=".hibiscus-extract-", dir=to))
        try:
            with zipfile.ZipFile(zpath) as zf:
                infos = zf.infolist()
                tops = {PurePosixPath(i.filename).parts[0] for i in infos if i.filename.strip("/")}
                if len(tops) != 1:
                    raise PullError(
                        f"bundle zip must have exactly one top-level directory, found {sorted(tops)}"
                    )
                top = tops.pop()
                for info in infos:
                    rel = _safe_rel(info.filename)
                    mode = (info.external_attr >> 16) & 0xFFFF
                    if stat.S_ISLNK(mode):
                        raise PullError(f"symlink in bundle: {info.filename}")
                    target = tmp / rel
                    if info.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(info) as src, target.open("wb") as dst:
                        shutil.copyfileobj(src, dst, CHUNK)
                    perm = stat.S_IMODE(mode)
                    os.chmod(target, 0o755 if perm & 0o111 else 0o644)
            return top, tmp / top
        except (zipfile.BadZipFile, PullError):
            shutil.rmtree(tmp, ignore_errors=True)
            raise

    @staticmethod
    def _replace(staged: Path, final: Path) -> None:
        if final.exists():
            backup = final.with_name(final.name + ".old")
            shutil.rmtree(backup, ignore_errors=True)
            final.rename(backup)
            staged.rename(final)
            shutil.rmtree(backup, ignore_errors=True)
        else:
            staged.rename(final)

    def _pull_files(self, model: dict[str, Any], to: Path, *, only: str, force: bool) -> PullResult:
        model_id = str(model["id"])
        manifest = self.api.list_model_files(model_id).to_dict()
        bundle_name = str(manifest["bundle_name"])
        _safe_rel(bundle_name)
        if "/" in bundle_name:
            raise PullError(f"invalid bundle_name {bundle_name!r}")
        final = to / bundle_name
        if not force:
            done = self._existing_ok(final, only)
            if done:
                return done
        files = [f for f in manifest["files"] if _selected(str(f["path"]), only)]
        if not files:
            raise PullError(f"no bundle files under {only!r}")
        partial = to / ".hibiscus-partial" / f"{model_id}-files"
        total = sum(int(f["size"]) for f in files)
        self.events.on_start(total, 0)
        fetched = 0
        for f in files:
            rel = _safe_rel(str(f["path"]))
            dest = partial / rel
            if dest.exists() and dest.stat().st_size == int(f["size"]) and sha256_file(dest) == f["sha256"]:
                self.events.on_bytes(int(f["size"]))
                continue
            sub = PullEvents(
                on_start=lambda t, h: None, on_bytes=self.events.on_bytes, on_info=self.events.on_info
            )
            saved, self.events = self.events, sub
            try:
                n, _ = self._download(
                    f"/models/{model_id}/files/{quote(str(f['path']), safe='')}",
                    dest,
                    etag=None,
                    expected_size=int(f["size"]),
                )
            finally:
                self.events = saved
            fetched += n
            if sha256_file(dest) != f["sha256"]:
                dest.unlink()
                raise PullError(f"sha256 mismatch for {f['path']}; partial removed, retry")
        (partial / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        checked, problems = verify_manifest(partial, strict_extra=False, only=only)
        if problems:
            raise PullError("MANIFEST verification failed: " + "; ".join(problems[:10]))
        final.parent.mkdir(parents=True, exist_ok=True)
        self._replace(partial, final)
        _rmdir_quiet(to / ".hibiscus-partial")
        return PullResult(final, bundle_name, checked, fetched)


def _rmdir_quiet(p: Path) -> None:
    try:
        p.rmdir()
    except OSError:
        pass
