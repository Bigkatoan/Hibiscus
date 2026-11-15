"""Validation report model (OpenAPI ``ValidationReport`` / ``ValidationStep`` / ``ValidationIssue``).

The worker builds one report per validation attempt. Steps are fixed and ordered
(``ValidationStepId``): checksum, unpack, structure, schema, decode, timestamps, stats.
"""

from __future__ import annotations

import enum
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

VALIDATOR_VERSION = "0.1.0"
MAX_ISSUES_PER_STEP = 500


class StepId(enum.StrEnum):
    CHECKSUM = "checksum"
    UNPACK = "unpack"
    STRUCTURE = "structure"
    SCHEMA = "schema"
    DECODE = "decode"
    TIMESTAMPS = "timestamps"
    STATS = "stats"


STEP_ORDER: tuple[StepId, ...] = tuple(StepId)


class Severity(enum.StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class IssueCode(enum.StrEnum):
    """Exactly the OpenAPI ``ValidationIssue.code`` enum."""

    CHECKSUM_MISMATCH = "checksum_mismatch"
    ARCHIVE_CORRUPT = "archive_corrupt"
    ARCHIVE_UNSAFE_PATH = "archive_unsafe_path"
    ARCHIVE_SYMLINK = "archive_symlink"
    ARCHIVE_BOMB = "archive_bomb"
    ARCHIVE_TOO_LARGE = "archive_too_large"
    DATASET_ROOT_NOT_FOUND = "dataset_root_not_found"
    MULTIPLE_DATASET_ROOTS = "multiple_dataset_roots"
    MISSING_FILE = "missing_file"
    INFO_JSON_INVALID = "info_json_invalid"
    UNSUPPORTED_CODEBASE_VERSION = "unsupported_codebase_version"
    CONVERSION_FAILED = "conversion_failed"
    FEATURE_MISSING = "feature_missing"
    FEATURE_SHAPE_INVALID = "feature_shape_invalid"
    JOINT_NAMES_MISMATCH = "joint_names_mismatch"
    NO_CAMERA = "no_camera"
    CAMERA_SHAPE_MISMATCH = "camera_shape_mismatch"
    VIDEO_MISSING = "video_missing"
    VIDEO_DECODE_FAILED = "video_decode_failed"
    FRAME_COUNT_MISMATCH = "frame_count_mismatch"
    TIMESTAMP_IRREGULAR = "timestamp_irregular"
    TIMESTAMP_FPS_MISMATCH = "timestamp_fps_mismatch"
    NAN_VALUES = "nan_values"
    STATS_MISSING = "stats_missing"
    STATS_MISMATCH = "stats_mismatch"
    EPISODE_TOO_SHORT = "episode_too_short"
    TASK_MISSING = "task_missing"


StepStatus = Literal["pending", "running", "passed", "warning", "failed", "skipped"]
SummaryResult = Literal["running", "passed", "passed_with_warnings", "failed"]


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(slots=True)
class Issue:
    code: IssueCode
    severity: Severity
    message: str
    params: dict[str, Any] = field(default_factory=dict)
    episode_index: int | None = None
    path: str | None = None
    feature: str | None = None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "code": self.code.value,
            "severity": self.severity.value,
            "message": self.message,
            "episode_index": self.episode_index,
            "path": self.path,
            "feature": self.feature,
        }
        if self.params:
            out["params"] = self.params
        return out


@dataclass(slots=True)
class Step:
    id: StepId
    status: StepStatus = "pending"
    started_at: str | None = None
    finished_at: str | None = None
    progress: float = 0.0
    issues: list[Issue] = field(default_factory=list)
    issues_truncated: int = 0
    errors: int = 0
    warnings: int = 0

    def add(self, issue: Issue) -> None:
        if issue.severity is Severity.ERROR:
            self.errors += 1
        elif issue.severity is Severity.WARNING:
            self.warnings += 1
        if len(self.issues) < MAX_ISSUES_PER_STEP:
            self.issues.append(issue)
        else:
            self.issues_truncated += 1

    def error(self, code: IssueCode, message: str, **kw: Any) -> None:
        self.add(Issue(code, Severity.ERROR, message, **kw))

    def warn(self, code: IssueCode, message: str, **kw: Any) -> None:
        self.add(Issue(code, Severity.WARNING, message, **kw))

    def info(self, code: IssueCode, message: str, **kw: Any) -> None:
        self.add(Issue(code, Severity.INFO, message, **kw))

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id.value,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "progress": round(min(max(self.progress, 0.0), 1.0), 4),
            "issues": [i.to_json() for i in self.issues],
        }
        if self.issues_truncated:
            out["issues_truncated"] = self.issues_truncated
        return out


class Report:
    """Mutable report; ``to_json`` yields the OpenAPI ``ValidationReport`` document."""

    def __init__(self, dataset_version_id: str, job_id: str | None, lerobot_version: str) -> None:
        self.dataset_version_id = dataset_version_id
        self.job_id = job_id
        self.lerobot_version = lerobot_version
        self.steps: dict[StepId, Step] = {sid: Step(sid) for sid in STEP_ORDER}
        self.recomputed_stats_max_rel_diff: dict[str, Any] | None = None
        self.finished = False

    def step(self, sid: StepId) -> Step:
        return self.steps[sid]

    @contextmanager
    def run(self, sid: StepId) -> Iterator[Step]:
        """Mark a step running; on exit it becomes passed / warning / failed from its issues."""
        st = self.steps[sid]
        st.status = "running"
        st.started_at = _now()
        try:
            yield st
        finally:
            st.finished_at = _now()
            st.progress = 1.0
            if st.errors:
                st.status = "failed"
            elif st.warnings:
                st.status = "warning"
            else:
                st.status = "passed"

    def skip(self, sid: StepId) -> None:
        st = self.steps[sid]
        if st.status in ("pending", "running"):
            st.status = "skipped"

    def skip_remaining(self) -> None:
        for st in self.steps.values():
            if st.status == "pending":
                st.status = "skipped"

    @property
    def errors(self) -> int:
        return sum(s.errors for s in self.steps.values())

    @property
    def warnings(self) -> int:
        return sum(s.warnings for s in self.steps.values())

    @property
    def failed(self) -> bool:
        return self.errors > 0

    def summary(self) -> dict[str, Any]:
        result: SummaryResult
        if not self.finished:
            result = "running"
        elif self.errors:
            result = "failed"
        elif self.warnings:
            result = "passed_with_warnings"
        else:
            result = "passed"
        return {"result": result, "errors": self.errors, "warnings": self.warnings}

    def issue_codes(self) -> set[str]:
        return {i.code.value for s in self.steps.values() for i in s.issues}

    def to_json(self) -> dict[str, Any]:
        return {
            "dataset_version_id": self.dataset_version_id,
            "job_id": self.job_id,
            "validator_version": VALIDATOR_VERSION,
            "lerobot_version": self.lerobot_version,
            "summary": self.summary(),
            "steps": [self.steps[s].to_json() for s in STEP_ORDER],
            "recomputed_stats_max_rel_diff": self.recomputed_stats_max_rel_diff,
        }
