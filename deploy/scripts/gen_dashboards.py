#!/usr/bin/env python3
"""Generate the provisioned Grafana dashboards (deploy/observability/grafana/dashboards/*.json).

The JSON files are committed; CI runs ``gen_dashboards.py --check`` so they never drift from this
source. Panels: queue depth, run states, GPU utilisation / VRAM / temperature / power, API request
rate / errors / latency, target health and error logs (Loki).

    deploy/scripts/gen_dashboards.py           # rewrite the JSON files
    deploy/scripts/gen_dashboards.py --check   # exit 1 if they are stale
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

OUT_DIR = Path(__file__).resolve().parent.parent / "observability" / "grafana" / "dashboards"
PROM = {"type": "prometheus", "uid": "prometheus"}
LOKI = {"type": "loki", "uid": "loki"}

Panel = dict[str, Any]


class Layout:
    """Places panels on Grafana's 24-column grid, row by row."""

    def __init__(self) -> None:
        self.y = 0
        self.x = 0
        self.row_h = 0
        self.next_id = 1
        self.panels: list[Panel] = []

    def row(self, title: str) -> None:
        self._newline()
        self.panels.append(
            {
                "type": "row",
                "title": title,
                "id": self._id(),
                "collapsed": False,
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": self.y},
                "panels": [],
            }
        )
        self.y += 1

    def add(self, panel: Panel, w: int, h: int) -> None:
        if self.x + w > 24:
            self._newline()
        panel["id"] = self._id()
        panel["gridPos"] = {"h": h, "w": w, "x": self.x, "y": self.y}
        self.panels.append(panel)
        self.x += w
        self.row_h = max(self.row_h, h)

    def _newline(self) -> None:
        if self.x:
            self.y += self.row_h
        self.x = 0
        self.row_h = 0

    def _id(self) -> int:
        i = self.next_id
        self.next_id += 1
        return i


def target(expr: str, legend: str = "", ref: str = "A", *, instant: bool = False) -> dict[str, Any]:
    t: dict[str, Any] = {"datasource": PROM, "expr": expr, "legendFormat": legend, "refId": ref}
    if instant:
        t["instant"] = True
        t["range"] = False
    return t


def timeseries(
    title: str,
    targets: list[dict[str, Any]],
    unit: str = "short",
    *,
    description: str = "",
    max_value: float | None = None,
    stack: bool = False,
) -> Panel:
    defaults: dict[str, Any] = {
        "unit": unit,
        "custom": {
            "lineWidth": 2,
            "fillOpacity": 10,
            "showPoints": "never",
            "stacking": {"mode": "normal" if stack else "none", "group": "A"},
        },
    }
    if max_value is not None:
        defaults["max"] = max_value
        defaults["min"] = 0
    return {
        "type": "timeseries",
        "title": title,
        "description": description,
        "datasource": PROM,
        "targets": targets,
        "fieldConfig": {"defaults": defaults, "overrides": []},
        "options": {
            "legend": {"displayMode": "list", "placement": "bottom"},
            "tooltip": {"mode": "multi", "sort": "desc"},
        },
    }


def stat(
    title: str,
    expr: str,
    unit: str = "short",
    *,
    description: str = "",
    thresholds: list[tuple[float | None, str]] | None = None,
    legend: str = "",
) -> Panel:
    steps = [{"color": c, "value": v} for v, c in (thresholds or [(None, "green")])]
    return {
        "type": "stat",
        "title": title,
        "description": description,
        "datasource": PROM,
        "targets": [target(expr, legend, instant=True)],
        "fieldConfig": {
            "defaults": {"unit": unit, "thresholds": {"mode": "absolute", "steps": steps}},
            "overrides": [],
        },
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "colorMode": "value",
            "graphMode": "area",
            "textMode": "auto",
            "orientation": "auto",
            "justifyMode": "auto",
        },
    }


def bargauge(title: str, expr: str, legend: str, *, description: str = "") -> Panel:
    return {
        "type": "bargauge",
        "title": title,
        "description": description,
        "datasource": PROM,
        "targets": [target(expr, legend, instant=True)],
        "fieldConfig": {
            "defaults": {
                "unit": "short",
                "min": 0,
                "thresholds": {"mode": "absolute", "steps": [{"color": "blue", "value": None}]},
            },
            "overrides": [],
        },
        "options": {
            "displayMode": "basic",
            "orientation": "horizontal",
            "showUnfilled": True,
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
        },
    }


def logs(title: str, expr: str) -> Panel:
    return {
        "type": "logs",
        "title": title,
        "datasource": LOKI,
        "targets": [{"datasource": LOKI, "expr": expr, "refId": "A"}],
        "options": {
            "showTime": True,
            "wrapLogMessage": True,
            "sortOrder": "Descending",
            "enableLogDetails": True,
            "dedupStrategy": "none",
        },
    }


def overview() -> dict[str, Any]:
    g = Layout()
    g.row("Queue & runs")
    g.add(
        stat(
            "Runs queued",
            "hibiscus_run_queue_queued",
            description="Training runs waiting for a GPU",
            thresholds=[(None, "green"), (3, "yellow"), (10, "red")],
        ),
        4,
        4,
    )
    g.add(stat("Runs active", "hibiscus_run_queue_active", description="Runs holding a GPU"), 4, 4)
    g.add(
        stat(
            "Oldest queued run",
            "hibiscus_run_queue_oldest_queued_seconds",
            "s",
            thresholds=[(None, "green"), (3600, "yellow"), (21600, "red")],
        ),
        4,
        4,
    )
    g.add(
        stat(
            "CPU jobs queued",
            'hibiscus_job_queue_queued{resource="cpu"}',
            description="validate / import / merge / hub push",
            thresholds=[(None, "green"), (5, "yellow"), (20, "red")],
        ),
        4,
        4,
    )
    g.add(
        stat(
            "GPU nodes online",
            "sum(hibiscus_gpu_node_online)",
            thresholds=[(None, "red"), (1, "yellow"), (2, "green")],
        ),
        4,
        4,
    )
    g.add(
        stat(
            "Firing alerts",
            'count(ALERTS{alertstate="firing"}) or vector(0)',
            thresholds=[(None, "green"), (1, "red")],
        ),
        4,
        4,
    )
    g.add(
        timeseries(
            "Queue depth",
            [
                target("hibiscus_run_queue_queued", "runs queued", "A"),
                target("hibiscus_job_queue_queued", "{{resource}} jobs queued", "B"),
                target("hibiscus_run_queue_active", "runs active", "C"),
            ],
        ),
        12,
        8,
    )
    g.add(
        bargauge(
            "Runs by state",
            "hibiscus_runs_runs",
            "{{status}}",
            description="Every run in the database by lifecycle status (run-lifecycle.md)",
        ),
        12,
        8,
    )
    g.add(
        timeseries(
            "Run states over time",
            [
                target(
                    'hibiscus_runs_runs{status=~"queued|preparing|running|pausing|paused|exporting|cancelling"}',
                    "{{status}}",
                )
            ],
            stack=True,
        ),
        12,
        8,
    )
    g.add(
        timeseries(
            "GPU node heartbeat age",
            [target("hibiscus_gpu_node_heartbeat_age_seconds", "{{node}} ({{status}})")],
            "s",
            description="Lease TTL is 60 s (ADR-0002)",
        ),
        12,
        8,
    )

    g.row("GPUs")
    gpu = "{{name}} ({{uuid}})"
    g.add(
        timeseries(
            "GPU utilisation", [target("nvidia_smi_utilization_gpu_ratio", gpu)], "percentunit", max_value=1
        ),
        12,
        8,
    )
    g.add(
        timeseries(
            "VRAM used",
            [
                target("nvidia_smi_memory_used_bytes", gpu + " used", "A"),
                target("nvidia_smi_memory_total_bytes", gpu + " total", "B"),
            ],
            "bytes",
        ),
        12,
        8,
    )
    g.add(timeseries("GPU temperature", [target("nvidia_smi_temperature_gpu", gpu)], "celsius"), 12, 8)
    g.add(timeseries("GPU power draw", [target("nvidia_smi_power_draw_watts", gpu)], "watt"), 12, 8)

    g.row("API")
    g.add(
        timeseries(
            "Requests / s by status class",
            [target("hibiscus:api_requests:rate5m", "{{status_class}}")],
            "reqps",
            stack=True,
        ),
        8,
        8,
    )
    g.add(
        timeseries(
            "5xx ratio", [target("hibiscus:api_5xx_ratio:rate5m", "5xx / all")], "percentunit", max_value=1
        ),
        8,
        8,
    )
    g.add(
        timeseries(
            "Latency",
            [
                target("hibiscus:api_latency_p95:5m", "p95", "A"),
                target(
                    "histogram_quantile(0.50, sum by (le) "
                    "(rate(hibiscus_http_request_duration_seconds_bucket[5m])))",
                    "p50",
                    "B",
                ),
            ],
            "s",
            description="Excludes upload parts and SSE streams; target p95 < 200 ms (PLAN §6)",
        ),
        8,
        8,
    )
    g.add(
        timeseries(
            "Top routes by 5xx",
            [
                target(
                    'topk(5, sum by (route) (rate(hibiscus_http_requests_total{status=~"5.."}[5m])))',
                    "{{route}}",
                )
            ],
            "reqps",
        ),
        12,
        8,
    )
    g.add(
        timeseries(
            "Top routes by p95 latency",
            [
                target(
                    "topk(5, histogram_quantile(0.95, sum by (le, route) "
                    "(rate(hibiscus_http_request_duration_seconds_bucket[5m]))))",
                    "{{route}}",
                )
            ],
            "s",
        ),
        12,
        8,
    )

    g.row("Platform")
    g.add(bargauge("Targets up", "up", "{{job}} {{instance}}"), 12, 8)
    g.add(
        timeseries(
            "Postgres connections",
            [target('sum by (state) (pg_stat_activity_count{datname="hibiscus"})', "{{state}}")],
        ),
        12,
        8,
    )
    g.add(
        logs(
            "Errors (all Hibiscus services)",
            '{project=~"hibiscus.*"} |~ "(?i)(\\"level\\":\\"(error|critical)\\"|traceback|exception)"',
        ),
        24,
        10,
    )

    return {
        "uid": "hibiscus-overview",
        "title": "Hibiscus overview",
        "tags": ["hibiscus"],
        "timezone": "browser",
        "schemaVersion": 39,
        "version": 1,
        "editable": False,
        "graphTooltip": 1,
        "refresh": "30s",
        "time": {"from": "now-6h", "to": "now"},
        "templating": {"list": []},
        "annotations": {"list": []},
        "links": [],
        "panels": g.panels,
    }


def logs_dashboard() -> dict[str, Any]:
    g = Layout()
    g.add(
        {
            "type": "timeseries",
            "title": "Log lines by service",
            "datasource": LOKI,
            "targets": [
                {
                    "datasource": LOKI,
                    "refId": "A",
                    "expr": "sum by (service) "
                    '(count_over_time({project=~"hibiscus.*", service=~"$service"}[1m]))',
                    "legendFormat": "{{service}}",
                }
            ],
            "fieldConfig": {"defaults": {"unit": "short"}, "overrides": []},
            "options": {},
        },
        24,
        7,
    )
    g.add(logs("Logs", '{project=~"hibiscus.*", service=~"$service"} |= "$search"'), 24, 18)
    return {
        "uid": "hibiscus-logs",
        "title": "Hibiscus logs",
        "tags": ["hibiscus"],
        "timezone": "browser",
        "schemaVersion": 39,
        "version": 1,
        "editable": False,
        "refresh": "30s",
        "time": {"from": "now-1h", "to": "now"},
        "templating": {
            "list": [
                {
                    "type": "query",
                    "name": "service",
                    "label": "service",
                    "datasource": LOKI,
                    "query": {"label": "service", "stream": '{project=~"hibiscus.*"}', "type": 1},
                    "includeAll": True,
                    "multi": True,
                    "allValue": ".+",
                    "refresh": 2,
                    "current": {"text": "All", "value": "$__all"},
                },
                {
                    "type": "textbox",
                    "name": "search",
                    "label": "contains (request_id, run_id, text)",
                    "query": "",
                    "current": {"text": "", "value": ""},
                },
            ]
        },
        "annotations": {"list": []},
        "links": [],
        "panels": g.panels,
    }


DASHBOARDS = {"hibiscus-overview.json": overview, "hibiscus-logs.json": logs_dashboard}


def render() -> dict[str, str]:
    return {name: json.dumps(fn(), indent=2, sort_keys=True) + "\n" for name, fn in DASHBOARDS.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    stale = []
    for name, text in render().items():
        path = OUT_DIR / name
        if args.check:
            if not path.exists() or path.read_text() != text:
                stale.append(name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    if stale:
        print(f"stale dashboards (run deploy/scripts/gen_dashboards.py): {stale}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
