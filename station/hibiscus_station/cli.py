"""``hibiscus-station`` entry point (spec §1.1, §8).

uvx hibiscus-station                 # start on 127.0.0.1:18210 and open the browser
hibiscus-station --mock --no-browser # demo mode with mock arms and cameras
hibiscus-station url                 # print a fresh login URL for the running instance
hibiscus-station openapi PATH        # write the OpenAPI document
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
import webbrowser
from pathlib import Path

import typer

from hibiscus_station import __version__
from hibiscus_station.settings import DEFAULT_PORT, StationPaths, station_home

app = typer.Typer(
    add_completion=False, help="Hibiscus Station: the local robot agent.", no_args_is_help=False
)
ALLOWED_HOSTS = ("127.0.0.1", "::1")


def _login_url(port: int, token: str, host: str = "127.0.0.1") -> str:
    h = f"[{host}]" if ":" in host else host
    return f"http://{h}:{port}/auth?t={token}"


def _setup_logging(paths: StationPaths, verbose: bool) -> None:
    from hibiscus_station.logs import RedactingFilter

    paths.logs.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        paths.logs / "station.log", maxBytes=10 * 1024**2, backupCount=5
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(threadName)s %(name)s: %(message)s"))
    handler.addFilter(RedactingFilter())
    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    console.addFilter(RedactingFilter())
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO, handlers=[handler, console], force=True
    )


@app.callback(invoke_without_command=True)
def serve(
    ctx: typer.Context,
    port: int = typer.Option(DEFAULT_PORT, "--port", help="Port on 127.0.0.1"),
    host: str = typer.Option("127.0.0.1", "--host", help="Only 127.0.0.1 or ::1 (no remote access in v1)"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Do not open the browser"),
    mock: bool = typer.Option(False, "--mock", help="Demo mode: mock arms, mock cameras"),
    home: Path | None = typer.Option(None, "--home", help="Data dir (default ~/.hibiscus/station)"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    version: bool = typer.Option(False, "--version"),
) -> None:
    if version:
        typer.echo(f"hibiscus-station {__version__}")
        raise typer.Exit(0)
    if ctx.invoked_subcommand is not None:
        return
    if host not in ALLOWED_HOSTS:
        typer.echo(
            f"--host {host}: remote access is not supported; Station binds 127.0.0.1 or ::1 only.", err=True
        )
        raise typer.Exit(2)
    import uvicorn

    from hibiscus_station.api.security import LocalAuth
    from hibiscus_station.app import create_app
    from hibiscus_station.hw.locks import DeviceBusyError, InstanceLock
    from hibiscus_station.station import Station

    paths = StationPaths(home or station_home())
    paths.ensure()
    lock = InstanceLock(paths.lock, paths.pid)
    try:
        lock.acquire()
    except DeviceBusyError:
        token = paths.token.read_text().strip() if paths.token.is_file() else ""
        running_port = _running_port(paths) or port
        typer.echo(f"Hibiscus Station is already running: {_login_url(running_port, token)}")
        raise typer.Exit(0) from None
    paths.pid.write_text(json.dumps({"pid": os.getpid(), "port": port, "host": host}))
    _setup_logging(paths, verbose)
    auth = LocalAuth(port=port)
    auth.write_token(paths.token)
    station = Station(paths.home, mock=mock, port=port)
    application = create_app(station, auth)
    url = _login_url(port, auth.token, host)
    typer.echo(f"Hibiscus Station {__version__}{' (mock)' if mock else ''}: {url}")
    if not no_browser:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: S110 - no browser on this machine: the URL is printed
            pass
    try:
        uvicorn.run(application, host=host, port=port, log_level="warning", access_log=False)
    finally:
        lock.release()


def _running_port(paths: StationPaths) -> int | None:
    try:
        data = json.loads(paths.pid.read_text())
        return int(data["port"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


@app.command()
def url(home: Path | None = typer.Option(None, "--home")) -> None:
    """Print a fresh login URL for the running Station."""
    paths = StationPaths(home or station_home())
    if not paths.token.is_file():
        typer.echo("Hibiscus Station is not running.", err=True)
        raise typer.Exit(1)
    port = _running_port(paths) or DEFAULT_PORT
    typer.echo(_login_url(port, paths.token.read_text().strip()))


@app.command()
def openapi(path: Path = typer.Argument(Path("openapi.json"))) -> None:
    """Write the OpenAPI document (committed as station/openapi.json)."""
    from hibiscus_station.openapi import export

    path.write_text(export())
    typer.echo(f"wrote {path}")


def main() -> None:
    app(prog_name="hibiscus-station")


if __name__ == "__main__":  # pragma: no cover
    main()
    sys.exit(0)
