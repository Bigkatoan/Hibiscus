"""Hatch build hook: ship the built Station SPA inside the wheel (spec §10 A8).

The SPA is built by the frontend (``vite build -c vite.station.config.ts`` -> ``frontend/dist-station``).
At wheel build time it is force-included as ``hibiscus_station/static``; a pre-populated
``hibiscus_station/static`` (e.g. from an sdist) is used when the dist is absent. The build fails
when neither exists, unless ``HIBISCUS_STATION_ALLOW_NO_WEB=1`` is set (API-only wheel).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):  # type: ignore[type-arg]
    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        if version == "editable":  # `uv sync` dev install: the SPA is optional
            return
        root = Path(self.root)
        static = root / "hibiscus_station" / "static"
        dist = root.parent / "frontend" / "dist-station"
        if (dist / "index.html").is_file():
            # Ship the fresh SPA build without copying it into the source tree.
            build_data["force_include"][str(dist)] = "hibiscus_station/static"
            return
        if (static / "index.html").is_file():  # sdist / pre-populated tree
            return
        if os.environ.get("HIBISCUS_STATION_ALLOW_NO_WEB") == "1":
            return
        raise RuntimeError(
            "frontend/dist-station is missing: build it first (frontend: pnpm build:station) "
            "or set HIBISCUS_STATION_ALLOW_NO_WEB=1 for an API-only wheel"
        )
