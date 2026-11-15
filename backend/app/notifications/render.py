"""vi/en text for external notification messages (in-app text is rendered by the SPA from ``kind``).

Param names follow CR-A7-2 (``run_number``, ``run_name``, ``model_name``, ``dataset_name``,
``version``, ``user_name``, ``workspace_name``, ``percent``) plus what the train worker writes
(``error_code``, ``silent_s``). Missing params render as ``?``; values are flattened to one short
line so user-controlled names cannot forge extra lines/markup in chat messages.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_TITLES: dict[str, dict[str, str]] = {
    "en": {
        "run.succeeded": "Run #{run_number} succeeded",
        "run.failed": "Run #{run_number} failed ({error_code})",
        "run.stalled": "Run #{run_number} looks stalled (no output for {silent_s} s)",
        "run.cancelled": "Run #{run_number} was cancelled",
        "model.ready": "Model {model_name} is ready",
        "model.failed": "Model export for run #{run_number} failed",
        "dataset.ready": "Dataset {dataset_name} v{version} is ready",
        "dataset.invalid": "Dataset {dataset_name} v{version} failed validation",
        "invite.accepted": "{user_name} joined {workspace_name}",
        "quota.warning": "GPU-hour quota at {percent}% in {workspace_name}",
        "test": "Hibiscus test notification: this channel works.",
    },
    "vi": {
        "run.succeeded": "Run #{run_number} đã hoàn tất",
        "run.failed": "Run #{run_number} thất bại ({error_code})",
        "run.stalled": "Run #{run_number} có vẻ bị treo (không có log trong {silent_s} giây)",
        "run.cancelled": "Run #{run_number} đã bị huỷ",
        "model.ready": "Model {model_name} đã sẵn sàng",
        "model.failed": "Xuất model cho run #{run_number} thất bại",
        "dataset.ready": "Dataset {dataset_name} v{version} đã sẵn sàng",
        "dataset.invalid": "Dataset {dataset_name} v{version} không hợp lệ",
        "invite.accepted": "{user_name} đã tham gia {workspace_name}",
        "quota.warning": "Đã dùng {percent}% hạn mức GPU-giờ trong {workspace_name}",
        "test": "Thông báo thử từ Hibiscus: kênh này hoạt động.",
    },
}
_FALLBACK = {"en": "Hibiscus notification: {kind}", "vi": "Thông báo Hibiscus: {kind}"}
_OPEN = {"en": "Open", "vi": "Mở"}
_CTRL = re.compile("[\x00-\x1f\x7f\u2028\u2029]+")


def locale_of(raw: str | None) -> str:
    return "en" if (raw or "").lower().startswith("en") else "vi"


def _clean(value: Any) -> str:
    s = _CTRL.sub(" ", str(value)).strip()
    return s if len(s) <= 120 else s[:119] + "…"


class _Params(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return "?"


@dataclass(frozen=True)
class Rendered:
    subject: str
    text: str
    title: str
    url: str | None


def render(kind: str, params: dict[str, Any], locale: str, url: str | None) -> Rendered:
    loc = locale_of(locale)
    tmpl = _TITLES[loc].get(kind)
    values = _Params({k: _clean(v) for k, v in (params or {}).items() if v is not None})
    title = tmpl.format_map(values) if tmpl else _FALLBACK[loc].format(kind=_clean(kind))
    text = title if not url else f"{title}\n{_OPEN[loc]}: {url}"
    return Rendered(subject=f"[Hibiscus] {title}", text=text, title=title, url=url)


def absolute_link(public_base_url: str, link: str | None, workspace_slug: str | None) -> str | None:
    """SPA path -> absolute URL. Workspace-relative paths get ``/w/<slug>`` (CR-A6-2)."""
    if not link or not link.startswith("/") or link.startswith("//") or "\\" in link:
        return None
    if workspace_slug and not link.startswith("/w/"):
        link = f"/w/{workspace_slug}{link}"
    return public_base_url.rstrip("/") + link
