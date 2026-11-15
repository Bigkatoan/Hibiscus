"""End-to-end validation of one dataset version on local disk (no DB / S3 here).

checksum -> unpack (sandboxed libarchive) -> [v2.1 -> v3.0 conversion] -> structure -> schema ->
decode -> timestamps -> stats -> previews -> content hash.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from validate import checks, lerobot_meta, preview
from validate.archive import UnpackLimits
from validate.hashing import FileEntry, hash_tree, sha256_file
from validate.lerobot_tools import (
    CONVERTIBLE_VERSIONS,
    SUPPORTED_VERSION,
    convert_v21_to_v30,
    lerobot_version,
)
from validate.report import IssueCode, Report, StepId
from validate.sandbox import unpack_sandboxed

ProgressFn = Callable[[StepId | str, float], None]
VersionStatus = Literal["ready", "invalid", "failed"]

# Weights of each stage in the overall job progress (sum = 1).
STAGE_WEIGHTS: dict[str, float] = {
    "checksum": 0.05,
    "unpack": 0.10,
    "structure": 0.05,
    "schema": 0.02,
    "decode": 0.25,
    "timestamps": 0.08,
    "stats": 0.02,
    "preview": 0.38,
    "hash": 0.05,
}


@dataclass(slots=True)
class PipelineInput:
    dataset_version_id: str
    workdir: Path
    job_id: str | None = None
    archive: Path | None = None  # upload object (checksum + unpack run)
    expected_sha256: str | None = None
    dataset_dir: Path | None = None  # already-unpacked dataset (HF import, merge, re-validate)
    limits: UnpackLimits = field(default_factory=UnpackLimits)
    make_previews: bool = True


@dataclass(slots=True)
class PipelineOutput:
    report: Report
    status: VersionStatus
    error_code: str | None = None
    dataset_root: Path | None = None
    derived_dir: Path | None = None
    content_hash: str | None = None
    files: list[FileEntry] = field(default_factory=list)
    size_bytes: int | None = None
    fields: dict[str, Any] = field(default_factory=dict)  # dataset_versions columns
    preview: dict[str, Any] | None = None


def _noop(_: StepId | str, __: float) -> None:
    return None


def run_pipeline(inp: PipelineInput, progress: ProgressFn = _noop) -> PipelineOutput:
    report = Report(inp.dataset_version_id, inp.job_id, lerobot_version())
    inp.workdir.mkdir(parents=True, exist_ok=True)
    out = PipelineOutput(report=report, status="invalid")

    def finish(status: VersionStatus, error_code: str | None = None) -> PipelineOutput:
        report.skip_remaining()
        report.finished = True
        out.status = status
        out.error_code = error_code
        return out

    # ---- checksum + unpack -------------------------------------------------------------------
    extract_dir = inp.workdir / "extract"
    if inp.archive is not None:
        with report.run(StepId.CHECKSUM) as st:
            size = max(inp.archive.stat().st_size, 1)
            seen = 0

            def tick(n: int) -> None:
                nonlocal seen
                seen += n
                st.progress = seen / size
                progress(StepId.CHECKSUM, seen / size)

            digest = sha256_file(inp.archive, tick)
            if inp.expected_sha256 is not None and digest != inp.expected_sha256:
                st.error(
                    IssueCode.CHECKSUM_MISMATCH,
                    "Uploaded file sha256 differs from the declared sha256",
                    params={"expected": inp.expected_sha256, "actual": digest},
                )
        if report.failed:
            return finish("failed", "upload_checksum_mismatch")
        with report.run(StepId.UNPACK) as st:
            res = unpack_sandboxed(inp.archive, extract_dir, inp.limits)
            if not res.ok:
                problem = res.problem
                if problem is None:
                    st.error(IssueCode.ARCHIVE_CORRUPT, "Unpacking failed")
                else:
                    st.error(
                        IssueCode(problem.code), problem.message, path=problem.path, params=problem.params
                    )
            out.fields["unpack"] = {"files": res.files, "bytes": res.bytes_written, "format": res.format_name}
        progress(StepId.UNPACK, 1.0)
        if report.failed:
            shutil.rmtree(extract_dir, ignore_errors=True)
            return finish("invalid")
        search_base = extract_dir
    elif inp.dataset_dir is not None:
        report.skip(StepId.CHECKSUM)
        report.skip(StepId.UNPACK)
        search_base = inp.dataset_dir
    else:
        raise ValueError("either archive or dataset_dir is required")

    # ---- structure (+ conversion) -------------------------------------------------------------
    meta: lerobot_meta.DatasetMeta | None = None
    root: Path | None = None
    with report.run(StepId.STRUCTURE) as st:
        roots = lerobot_meta.find_dataset_roots(search_base)
        if not roots:
            st.error(IssueCode.DATASET_ROOT_NOT_FOUND, "No directory containing meta/info.json was found")
        elif len(roots) > 1:
            st.error(
                IssueCode.MULTIPLE_DATASET_ROOTS,
                "More than one dataset root in the archive",
                params={"roots": [r.relative_to(search_base).as_posix() for r in roots[:20]]},
            )
        else:
            root = roots[0]
            try:
                info = lerobot_meta.load_info(root)
                version = str(info.get("codebase_version"))
                if version in CONVERTIBLE_VERSIONS:
                    conv = convert_v21_to_v30(root)
                    if not conv.ok:
                        st.error(
                            IssueCode.CONVERSION_FAILED, f"v2.1 -> v3.0 conversion failed: {conv.message}"
                        )
                    else:
                        out.fields["converted_from"] = version
                elif version != SUPPORTED_VERSION:
                    st.error(
                        IssueCode.UNSUPPORTED_CODEBASE_VERSION,
                        f"codebase_version {version} is not supported (v3.0, or v2.1 with conversion)",
                        path="meta/info.json",
                        params={"codebase_version": version},
                    )
                if not st.errors:
                    meta = lerobot_meta.load_meta(root)
                    checks.check_structure(meta, st)
            except lerobot_meta.MetaError as exc:
                st.error(IssueCode(exc.code), str(exc), path=exc.path, params=exc.params)
    progress(StepId.STRUCTURE, 1.0)
    if meta is None or root is None:
        return finish("invalid")
    out.dataset_root = root
    out.fields.update(
        {
            "codebase_version": str(meta.info.get("codebase_version")),
            "robot_type": meta.info.get("robot_type"),
            "fps": meta.fps,
            "total_episodes": len(meta.episodes),
            "total_frames": sum(e.length for e in meta.episodes),
            "camera_keys": meta.camera_keys,
            "features": meta.features,
            "info": meta.info,
            "joint_names": checks.joint_names(meta),
            "tasks": meta.tasks,
        }
    )

    # ---- schema / decode / timestamps / stats ------------------------------------------------
    with report.run(StepId.SCHEMA) as st:
        checks.check_schema(meta, st)
    progress(StepId.SCHEMA, 1.0)

    codecs: dict[str, dict[str, Any]] = {}
    with report.run(StepId.DECODE) as st:

        def dprog(f: float) -> None:
            st.progress = f
            progress(StepId.DECODE, f)

        codecs = checks.check_decode(meta, st, dprog)

    with report.run(StepId.TIMESTAMPS) as st:

        def tprog(f: float) -> None:
            st.progress = f
            progress(StepId.TIMESTAMPS, f)

        scan = checks.check_timestamps(meta, st, tprog)

    with report.run(StepId.STATS) as st:
        try:
            stats = lerobot_meta.load_stats(root)
        except (ValueError, UnicodeDecodeError):
            stats = None
        out.fields["stats"] = stats
        report.recomputed_stats_max_rel_diff = checks.check_stats(meta, stats, scan, st) or None
    progress(StepId.STATS, 1.0)

    # ---- previews (never block) --------------------------------------------------------------
    if inp.make_previews:
        derived = inp.workdir / "derived"
        issue_eps = {
            i.episode_index for s in report.steps.values() for i in s.issues if i.episode_index is not None
        }

        def pprog(f: float) -> None:
            progress("preview", f)

        pres = preview.build_previews(
            meta, scan, codecs, derived, inp.dataset_version_id, report.step(StepId.DECODE), issue_eps, pprog
        )
        # Late preview warnings must be reflected in the decode step status.
        dstep = report.step(StepId.DECODE)
        if dstep.status == "passed" and dstep.warnings:
            dstep.status = "warning"
        out.preview = pres.preview
        out.derived_dir = derived

    # ---- content hash ------------------------------------------------------------------------
    content_hash, files = hash_tree(root)
    out.content_hash = content_hash
    out.files = files
    out.size_bytes = sum(f.size for f in files)
    progress("hash", 1.0)
    return finish("invalid" if report.failed else "ready")
