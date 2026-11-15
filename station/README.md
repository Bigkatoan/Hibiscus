# Hibiscus Station

Hibiscus Station is the local agent that runs on the computer wired to the robot. It connects an
SO-100 / SO-101 follower (and leader) arm, calibrates them, adds cameras, teleoperates, records
LeRobot datasets, uploads them to a Hibiscus workspace, pulls trained model bundles and **runs them on
the robot**. Specification: [`docs/spec/station.md`](../docs/spec/station.md). Licence: AGPL-3.0.

Two things LeLab does not do are first-class here:

* **R1 motor health.** Temperature, voltage, current, load and the alarm byte of every motor (follower
  and leader) are read inside the control loop without disturbing it, coloured against thresholds
  (warn 50 °C, hot 60 °C, critical 65 °C on two samples in a row, always at least 3 °C below the
  servo's own `Max_Temperature_Limit`) and logged per session and per episode. A critical reading
  stops the robot safely: hold, park at the rest pose when possible, torque off.
* **R2 cameras while a model runs.** One owner per camera feeds both the control loop and the UI, so
  every camera is visible during teleop, recording, replay and model runs. The preview of a run is
  made from the exact frames handed to the policy on that tick, tagged with the tick number.

## Install and run

```bash
# one-shot, from PyPI once published
uvx hibiscus-station

# or install the command
uv tool install hibiscus-station
hibiscus-station

# from this repository (no hardware needed in --mock)
uvx --from ./station hibiscus-station --mock --no-browser
```

Station listens on `127.0.0.1:18210` only and opens the browser on a one-time login link
(`/auth?t=...`). `hibiscus-station url` prints a fresh link for a running instance. Options:
`--port`, `--no-browser`, `--mock` (mock arms and cameras), `--home DIR` (default
`~/.hibiscus/station`, or `$HIBISCUS_STATION_HOME`), `--verbose`. A second launch prints the URL of the
instance already running and exits.

Optional extras: `hibiscus-station[realsense]`, `[smolvla]`, `[diffusion]`, `[pi]`.

### The web UI

The UI is a separate Vite build of the frontend (`frontend`, `pnpm build:station` →
`frontend/dist-station`). Build it **before** building or installing the station wheel; the hatch
build hook then ships it inside the wheel as `hibiscus_station/static/`:

```bash
frontend/scripts/node.sh pnpm install --frozen-lockfile   # Node via docker on hosts without Node
frontend/scripts/node.sh pnpm build:station
uvx --from ./station hibiscus-station --mock               # or: uv tool install ./station
hibiscus station --mock                                    # the same, through the Hibiscus CLI
```

Without the dist the wheel build fails, unless `HIBISCUS_STATION_ALLOW_NO_WEB=1` (API-only wheel). In
a source checkout (`uv run hibiscus-station`) Station serves `frontend/dist-station` directly;
`HIBISCUS_STATION_STATIC=DIR` overrides the directory. For UI development run
`pnpm dev:station` (`127.0.0.1:18211`, proxies `/api` and `/auth` to `127.0.0.1:18210`) and log in
through `http://127.0.0.1:18211/auth?t=<token>` (`hibiscus-station url` prints the token link).

### API contract

Every wire shape is a pydantic model in `hibiscus_station/api/schemas.py`, exported (REST and the
WebSocket messages) to `openapi.json`. The frontend's TypeScript types are generated from it:

```bash
env -u PYTHONPATH -u AMENT_PREFIX_PATH uv run hibiscus-station openapi openapi.json
frontend/scripts/node.sh pnpm gen:station-api    # → frontend/src/features/station/api/schema.d.ts
```

## Development

```bash
cd station
env -u PYTHONPATH -u AMENT_PREFIX_PATH uv sync
env -u PYTHONPATH -u AMENT_PREFIX_PATH uv run pytest              # CPU only, no devices
env -u PYTHONPATH -u AMENT_PREFIX_PATH uv run pytest -m slow      # + the real ACT checkpoint
env -u PYTHONPATH -u AMENT_PREFIX_PATH uv run ruff check . && uv run ruff format --check .
env -u PYTHONPATH -u AMENT_PREFIX_PATH uv run mypy hibiscus_station
env -u PYTHONPATH -u AMENT_PREFIX_PATH uv run hibiscus-station openapi openapi.json   # contract file
# browser end-to-end test (needs frontend/dist-station and `uv run playwright install chromium`)
env -u PYTHONPATH -u AMENT_PREFIX_PATH uv run pytest tests/e2e -m e2e
```

The e2e test starts a real `hibiscus-station --mock` (mock follower, leader and two mock cameras),
drives the UI through connect → calibrate → cameras → teleop → thermal safe stop → record (→ ← Esc)
→ import the ACT checkpoint → run with the Space e-stop, and saves screenshots to
`docs/ux/screenshots/station/`.

Layout: `hw/` (the hardware-owner thread, control loop, telemetry, safety, cameras, calibration),
`sessions/` (teleop, record, replay, run), `models/` (import, registry, compat, loader), `data/`
(datasets catalog, telemetry sidecars, session logs), `remote.py` (pairing, upload, pull through the
Hibiscus CLI), `api/` (REST, WebSockets, local security), `mock/` (mock bus, arms, cameras, dummy ACT
policy). Hardware acceptance: [`tests/hil/README.md`](tests/hil/README.md) and the user guide
`docs/user-guide/{en,vi}/station-hardware-uat.md`.
