"""``hibiscus`` command line (Typer). See cli/README.md for the user guide."""

from __future__ import annotations

import json
import os
import secrets
import shutil
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx
import typer
from rich.console import Console
from rich.markup import escape
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TaskID,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.table import Table

from hibiscus import __version__
from hibiscus._generated.models.run_create import RunCreate
from hibiscus.api import ApiError, HibiscusApi
from hibiscus.archive import DEFAULT_EXCLUDES, FileSource, VirtualTar, make_source
from hibiscus.config import Config, normalize_server
from hibiscus.credentials import (
    CredentialError,
    delete_token,
    load_token,
    looks_like_pat,
    save_token,
    token_prefix,
)
from hibiscus.logs import LogFollower, LogSink
from hibiscus.overrides import OverrideError, build_config
from hibiscus.pull import Puller, PullError, PullEvents
from hibiscus.resolve import (
    ResolveError,
    resolve_dataset,
    resolve_dataset_version,
    resolve_model_id,
    resolve_run_id,
)
from hibiscus.upload import MIB, Uploader, UploadError, UploadEvents, UploadResult
from hibiscus.watch import Watcher

app = typer.Typer(
    name="hibiscus",
    help="Hibiscus CLI — push LeRobot datasets, train policies, follow logs, pull model bundles.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    add_completion=False,
)
datasets_app = typer.Typer(help="List and inspect datasets.", no_args_is_help=True)
runs_app = typer.Typer(help="List and inspect training runs.", no_args_is_help=True)
models_app = typer.Typer(help="List exported models.", no_args_is_help=True)
app.add_typer(datasets_app, name="datasets")
app.add_typer(runs_app, name="runs")
app.add_typer(models_app, name="models")

out = Console(highlight=False, soft_wrap=True)
err = Console(stderr=True, highlight=False, soft_wrap=True)

HINTS = {
    "unauthenticated": "token missing or invalid: run `hibiscus login`",
    "token_revoked": "this token was revoked: create a new PAT in the web UI and run `hibiscus login`",
    "token_expired": "this token expired: create a new PAT and run `hibiscus login`",
    "insufficient_scope": "the PAT lacks a scope for this command (push: datasets:write, train: runs:write, "
    "logs/runs: runs:read, pull: models:read)",
    "quota_exceeded": "workspace quota reached: ask a workspace admin",
    "preflight_failed": "the run would fail; see the checks above (`hibiscus train ... --preflight-only`)",
    "model_not_ready": "the model bundle is still being built; retry later",
    "dataset_version_not_ready": "dataset validation has not finished (`hibiscus datasets show <name>`)",
}


def esc(value: object) -> str:
    """Escape server/user-provided text so rich never interprets ``[...]`` in it as markup."""
    return escape(str(value))


class SafeTable(Table):
    """Table whose cells are always plain text (server strings may contain ``[``)."""

    def add_row(self, *renderables: Any, **kwargs: Any) -> None:
        super().add_row(*(esc(r) if isinstance(r, str) else r for r in renderables), **kwargs)


class State:
    server_override: str | None = None


STATE = State()


def fail(msg: str, code: int = 1) -> typer.Exit:
    err.print(f"[bold red]error:[/] {esc(msg)}")
    return typer.Exit(code)


@contextmanager
def handle_errors() -> Iterator[None]:
    try:
        yield
    except ApiError as exc:
        err.print(f"[bold red]error:[/] {esc(exc)}")
        if exc.body and exc.body.get("errors"):
            for fe in exc.body["errors"][:20]:
                loc = ".".join(str(x) for x in fe.get("loc", []))
                err.print(f"  - {esc(loc)}: {esc(fe.get('message'))} {esc('[' + str(fe.get('code')) + ']')}")
        hint = HINTS.get(exc.code)
        if hint:
            err.print(f"[yellow]hint:[/] {esc(hint)}")
        raise typer.Exit(1) from exc
    except (ResolveError, UploadError, PullError, OverrideError, CredentialError, FileNotFoundError) as exc:
        raise fail(str(exc)) from exc
    except httpx.TransportError as exc:
        raise fail(f"network error: {type(exc).__name__}: {exc}") from exc


def _config() -> Config:
    cfg = Config.load()
    if STATE.server_override:
        cfg.server = normalize_server(STATE.server_override)
    return cfg


def _api(cfg: Config | None = None) -> HibiscusApi:
    cfg = cfg or _config()
    stored = load_token(cfg.server)
    if stored is None:
        raise fail(f"not logged in to {cfg.server}: run `hibiscus login`")
    if not cfg.workspace_id:
        raise fail("no workspace recorded: run `hibiscus login` again")
    return HibiscusApi(cfg.server, stored.token, workspace_id=cfg.workspace_id)


def _print_json(data: Any) -> None:
    # Machine-readable output stays plain: rich's print_json highlights by default, and with
    # FORCE_COLOR (CI) or a TTY that wraps keys/values in ANSI codes `jq` cannot parse.
    out.file.write(json.dumps(data, default=str, indent=2) + "\n")
    out.file.flush()


def _short(ts: Any) -> str:
    return str(ts)[:16].replace("T", " ") if ts else "-"


def _human(n: Any) -> str:
    if not isinstance(n, (int, float)):
        return "-"
    size = float(n)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return str(n)


# ====================================================================================== root
def _version_cb(value: bool) -> None:
    if value:
        out.print(f"hibiscus {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    server: str | None = typer.Option(
        None, "--server", envvar="HIBISCUS_SERVER", help="API URL, e.g. https://robot.example.com"
    ),
    version: bool = typer.Option(False, "--version", callback=_version_cb, is_eager=True),
) -> None:
    STATE.server_override = server


# ====================================================================================== auth
@app.command()
def login(
    token: str | None = typer.Option(None, "--token", help="PAT (hbp_…); prompted (hidden) if omitted"),
    server: str | None = typer.Option(None, "--server", help="API URL (default: saved or production)"),
) -> None:
    """Store a Personal Access Token (keyring, or ~/.config/hibiscus/credentials.json 0600)."""
    cfg = _config()
    if server:
        cfg.server = normalize_server(server)
    if token is None:
        token = typer.prompt("Personal Access Token", hide_input=True)
    token = token.strip()
    if not looks_like_pat(token):
        raise fail("that does not look like a Hibiscus PAT (expected hbp_<8 chars>_<43 chars>)")
    with handle_errors(), HibiscusApi(cfg.server, token) as api:
        me = api.me().to_dict()
    if me.get("auth_method") != "pat" or not me.get("token"):
        raise fail("the server did not accept this as a PAT")
    tok = me["token"]
    cfg.workspace_id = str(tok["workspace_id"])
    ws_name = next(
        (m["workspace_name"] for m in me.get("memberships", []) if m["workspace_id"] == cfg.workspace_id),
        None,
    )
    cfg.workspace_name = ws_name
    cfg.user_display_name = me["user"]["display_name"]
    cfg.token_prefix = token_prefix(token)
    with handle_errors():
        where = save_token(cfg.server, token)
    cfg.save()
    scopes = ", ".join(tok.get("scopes", []))
    out.print(
        f"[green]Logged in[/] to {esc(cfg.server)} as [bold]{esc(cfg.user_display_name)}[/] "
        f"(workspace {esc(ws_name or cfg.workspace_id)}; scopes: {esc(scopes)})"
    )
    out.print(f"Token stored in {esc(where)}.")
    if tok.get("expires_at"):
        out.print(f"Token expires at {esc(_short(tok['expires_at']))} UTC.")


@app.command()
def logout() -> None:
    """Remove the stored token for the current server."""
    cfg = _config()
    with handle_errors():
        removed = delete_token(cfg.server)
    out.print("Logged out." if removed else "No stored token.")


@app.command()
def whoami() -> None:
    """Show the user, workspace and token scopes for the stored token."""
    cfg = _config()
    with handle_errors(), _api(cfg) as api:
        me = api.me().to_dict()
    tok = me.get("token") or {}
    out.print(f"server:    {esc(cfg.server)}")
    out.print(f"user:      {esc(me['user']['display_name'])} <{esc(me['user']['email'])}>")
    out.print(f"workspace: {esc(cfg.workspace_name or '')} {esc(cfg.workspace_id)}")
    out.print(
        f"token:     hbp_{esc(tok.get('prefix', '?'))}_… scopes: {esc(', '.join(tok.get('scopes', [])))}"
    )


# ====================================================================================== push
def _make_progress() -> Progress:
    return Progress(
        TextColumn("[bold]{task.description}"),
        BarColumn(),
        DownloadColumn(binary_units=True),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=err,
        transient=False,
    )


def _do_push(
    api: HibiscusApi,
    src: FileSource | VirtualTar,
    *,
    dataset_id: str | None,
    new_name: str | None,
    part_size_mib: int,
    parallel: int,
) -> UploadResult:
    with _make_progress() as progress:
        tasks: dict[str, TaskID] = {}

        def hash_start(total: int) -> None:
            tasks["hash"] = progress.add_task("hashing", total=total)

        def hash_prog(n: int) -> None:
            progress.advance(tasks["hash"], n)

        def up_start(total: int, already: int) -> None:
            tasks["up"] = progress.add_task("uploading", total=total, completed=already)

        def part_done(part: int, n: int) -> None:
            progress.advance(tasks["up"], n)

        def retry(part: int, attempt: int, exc: BaseException, delay: float) -> None:
            progress.console.print(f"[yellow]part {part}: {esc(exc)} — retry {attempt} in {delay:.0f}s")

        events = UploadEvents(
            on_hash_start=hash_start,
            on_hash_progress=hash_prog,
            on_upload_start=up_start,
            on_part_done=part_done,
            on_retry=retry,
            on_info=lambda m: progress.console.print(f"[dim]{esc(m)}"),
        )
        uploader = Uploader(api, parallel=parallel, events=events)
        return uploader.push(
            src, dataset_id=dataset_id, new_dataset_name=new_name, part_size=part_size_mib * MIB
        )


def _target(
    api: HibiscusApi, dataset: str | None, name: str | None, default_name: str
) -> tuple[str | None, str | None]:
    if dataset and name:
        raise fail("use either --dataset (new version of an existing dataset) or --name (new dataset)")
    if dataset:
        return str(resolve_dataset(api, dataset)["id"]), None
    return None, (name or default_name)[:100]


def _wait_version(api: HibiscusApi, version_id: str, timeout_s: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last = ""
    while True:
        v = api.get_dataset_version(version_id)
        if v["status"] != last:
            err.print(f"[dim]version status: {esc(v['status'])}")
            last = v["status"]
        if v["status"] in ("ready", "invalid", "failed") or time.monotonic() > deadline:
            return v
        time.sleep(5)


@app.command()
def push(
    path: Path = typer.Argument(
        ..., exists=True, help="LeRobot dataset directory or archive (.zip/.tar/.rar…)"
    ),
    name: str | None = typer.Option(
        None, "--name", "-n", help="Name of the new dataset (default: dir/file name)"
    ),
    dataset: str | None = typer.Option(None, "--dataset", "-d", help="Add a new version to this dataset"),
    part_size: int = typer.Option(
        64, "--part-size", min=5, max=64, help="Part size in MiB (≤ 64, Cloudflare)"
    ),
    parallel: int = typer.Option(2, "--parallel", "-j", min=1, max=8, help="Parts uploaded concurrently"),
    exclude: list[str] = typer.Option([], "--exclude", help="Extra file/dir names to skip when tarring"),
    wait: bool = typer.Option(False, "--wait", help="Wait for server-side validation to finish"),
    wait_timeout: float = typer.Option(3600, "--wait-timeout", help="Seconds to wait with --wait"),
    as_json: bool = typer.Option(False, "--json", help="Print the result as JSON"),
) -> None:
    """Upload a dataset (resumable; re-run the same command to resume after an interruption)."""
    with handle_errors(), _api() as api:
        src = make_source(path, DEFAULT_EXCLUDES | frozenset(exclude))
        default_name = path.resolve().name if path.is_dir() else path.name.split(".")[0]
        ds_id, new_name = _target(api, dataset, name, default_name)
        if isinstance(src, VirtualTar):
            err.print(
                f"[dim]{esc(path)}: {src.file_count} files -> {esc(src.name)} ({_human(src.size)}, tar)"
            )
        res = _do_push(
            api, src, dataset_id=ds_id, new_name=new_name, part_size_mib=part_size, parallel=parallel
        )
        result: dict[str, Any] = dict(res.__dict__)
        if wait:
            v = _wait_version(api, res.version_id, wait_timeout)
            result["version_status"] = v["status"]
    if as_json:
        _print_json(result)
    else:
        out.print(
            f"[green]Uploaded[/] {_human(res.size)} -> dataset "
            f"[bold]{esc(res.dataset_name)}[/] v{res.version} "
            f"(version {esc(res.version_id)}; validation job {esc(res.job_id)}; "
            f"{res.sent_parts} parts sent, {res.resumed_parts} resumed)"
        )
        if "version_status" in result:
            out.print(f"Validation result: [bold]{esc(result['version_status'])}[/]")
    if wait and result.get("version_status") in ("invalid", "failed"):
        raise typer.Exit(1)


# ====================================================================================== watch
@app.command()
def watch(
    directory: Path = typer.Argument(..., exists=True, file_okay=False, help="Recording root to watch"),
    dataset: str | None = typer.Option(
        None, "--dataset", "-d", help="Upload every recording as a version of this dataset"
    ),
    name_prefix: str = typer.Option("", "--name-prefix", help="Prefix for new dataset names"),
    interval: float = typer.Option(10.0, "--interval", min=1.0, help="Seconds between scans"),
    debounce: float = typer.Option(30.0, "--debounce", min=0.0, help="Seconds without changes before upload"),
    part_size: int = typer.Option(64, "--part-size", min=5, max=64),
    parallel: int = typer.Option(2, "--parallel", "-j", min=1, max=8),
    once: bool = typer.Option(False, "--once", help="Scan until nothing is settling, then exit"),
) -> None:
    """Upload completed LeRobot v3.0 recordings found under DIRECTORY, each exactly once."""
    with handle_errors(), _api() as api:
        ds_id = str(resolve_dataset(api, dataset)["id"]) if dataset else None

        def do_push(src: VirtualTar, root: Path, previous_dataset_id: str | None) -> UploadResult:
            target = ds_id or previous_dataset_id
            new_name = None if target else f"{name_prefix}{root.name}"[:100]
            try:
                return _do_push(
                    api, src, dataset_id=target, new_name=new_name, part_size_mib=part_size, parallel=parallel
                )
            except ApiError as exc:
                if exc.code != "dataset_name_taken" or new_name is None:
                    raise
                existing = str(resolve_dataset(api, new_name)["id"])  # same name: add a version instead
                return _do_push(
                    api, src, dataset_id=existing, new_name=None, part_size_mib=part_size, parallel=parallel
                )

        def on_event(kind: str, p: Path, msg: str) -> None:
            color = {"uploaded": "green", "failed": "red", "uploading": "cyan"}.get(kind, "dim")
            err.print(f"[{color}]{time.strftime('%H:%M:%S')} {esc(kind)}[/] {esc(p)}: {esc(msg)}")

        w = Watcher(directory, do_push, debounce_s=debounce, on_event=on_event)
        err.print(f"Watching {esc(directory.resolve())} (debounce {debounce:.0f}s, Ctrl-C to stop)")
        try:
            while True:
                report = w.scan()
                settling = [r for r in report.waiting.values() if r.startswith(("settling", "retrying"))]
                if once and not settling:
                    break
                time.sleep(interval)
        except KeyboardInterrupt:
            err.print("stopped")


# ====================================================================================== datasets
@datasets_app.command("ls")
def datasets_ls(
    q: str | None = typer.Option(None, "--q", help="Name substring"),
    limit: int = typer.Option(50, "--limit", min=1, max=200),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """List datasets in the workspace."""
    with handle_errors(), _api() as api:
        page = api.list_datasets(q=q, limit=limit).to_dict()
    if as_json:
        _print_json(page)
        return
    t = SafeTable("name", "versions", "latest", "status", "episodes", "size", "updated", "id")
    for d in page["items"]:
        lv = d.get("latest_version") or {}
        t.add_row(
            d["name"],
            str(d["version_count"]),
            f"v{lv['version']}" if lv else "-",
            str(lv.get("status", "-")),
            str(lv.get("total_episodes") or "-"),
            _human(lv.get("size_bytes")),
            _short(d.get("updated_at")),
            str(d["id"]),
        )
    out.print(t)


@datasets_app.command("show")
def datasets_show(
    ref: str = typer.Argument(..., help="Dataset name or id"),
    version: int | None = typer.Option(None, "--version", "-v", help="Show this version in detail"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Show a dataset, its versions and the selected version's schema / validation."""
    with handle_errors(), _api() as api:
        ds = resolve_dataset(api, ref)
        versions = api.list_dataset_versions(str(ds["id"]), limit=50).to_dict()["items"]
        detail: dict[str, Any] | None = None
        if versions:
            _, detail = resolve_dataset_version(api, str(ds["id"]), version)
    if as_json:
        _print_json({"dataset": ds, "versions": versions, "version_detail": detail})
        return
    out.print(f"[bold]{esc(ds['name'])}[/]  ({esc(ds['id'])})  {esc(ds.get('description') or '')}")
    t = SafeTable("version", "status", "source", "episodes", "frames", "fps", "size", "created", "id")
    for v in versions:
        t.add_row(
            f"v{v['version']}",
            v["status"],
            v["source"],
            str(v.get("total_episodes") or "-"),
            str(v.get("total_frames") or "-"),
            str(v.get("fps") or "-"),
            _human(v.get("size_bytes")),
            _short(v.get("created_at")),
            str(v["id"]),
        )
    out.print(t)
    if detail:
        vs = detail.get("validation_summary") or {}
        out.print(
            f"v{detail['version']}: robot_type={esc(detail.get('robot_type'))} "
            f"codebase={esc(detail.get('codebase_version'))}"
            f" state_dim={detail.get('state_dim')} action_dim={detail.get('action_dim')}"
        )
        out.print(f"  cameras: {esc(', '.join(detail.get('camera_keys') or []) or '-')}")
        if detail.get("tasks"):
            out.print(f"  tasks: {'; '.join(detail['tasks'][:5])}")
        if vs:
            out.print(
                f"  validation: {esc(vs.get('result'))} "
                f"({vs.get('errors')} errors, {vs.get('warnings')} warnings)"
            )
        if detail.get("error_code"):
            out.print(f"  [red]error: {esc(detail['error_code'])}")


# ====================================================================================== train
def _schema_props(schema: dict[str, Any]) -> set[str]:
    props = schema.get("properties")
    return set(props) if isinstance(props, dict) else set()


@app.command()
def train(
    dataset: str = typer.Option(..., "--dataset", "-d", help="Dataset name/id, or a dataset-version id"),
    policy: str = typer.Option(
        ..., "--policy", "-p", help="act, diffusion, vqbet, tdmpc, smolvla, pi0, pi05"
    ),
    preset: str | None = typer.Option(None, "--preset", help="quick | standard | finetune"),
    sets: list[str] = typer.Option([], "--set", "-s", help="Override, e.g. train.steps=300 or chunk_size=50"),
    version: int | None = typer.Option(
        None, "--version", "-v", help="Dataset version number (default: latest)"
    ),
    name: str | None = typer.Option(None, "--name", help="Run name"),
    gpu: str = typer.Option("auto", "--gpu", help="auto or a GPU id (cuda0, cuda1)"),
    heldout: float | None = typer.Option(
        None, "--heldout", min=0.0, max=0.49, help="Held-out episode fraction"
    ),
    seed: int | None = typer.Option(None, "--seed", min=0),
    init_from_model: str | None = typer.Option(None, "--init-from-model", help="Fine-tune from a model id"),
    init_from_hf: str | None = typer.Option(None, "--init-from-hf", help="Fine-tune from a Hub repo id"),
    preflight_only: bool = typer.Option(False, "--preflight-only", help="Only run the checks"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow logs after creating the run"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Create a training run (runs preflight first; blockers abort)."""
    if preset is not None and preset not in ("quick", "standard", "finetune"):
        raise fail("--preset must be quick, standard or finetune")
    with handle_errors(), _api() as api:
        pol = api.get_policy(policy).to_dict()
        if not pol.get("trainable", True):
            raise fail(f"policy {policy} is not trainable on this server")
        config = build_config(
            sets,
            policy_props=_schema_props(pol.get("policy_schema") or {}),
            train_props=_schema_props(pol.get("train_schema") or {}),
        )
        ds, ver = resolve_dataset_version(api, dataset, version)
        if ver["status"] != "ready":
            err.print(
                f"[yellow]warning:[/] dataset version v{ver['version']} is {esc(ver['status'])}, not ready"
            )
        body: dict[str, Any] = {
            "workspace_id": str(api.ws()),
            "dataset_version_id": str(ver["id"]),
            "policy_type": policy,
            "config": config,
            "gpu": gpu,
        }
        if name:
            body["name"] = name
        if preset:
            body["preset"] = preset
        if heldout is not None:
            body["heldout_fraction"] = heldout
        if seed is not None:
            body["seed"] = seed
        if init_from_model and init_from_hf:
            raise fail("use only one of --init-from-model / --init-from-hf")
        if init_from_model:
            body["init_from"] = {"model_id": resolve_model_id(api, init_from_model)}
        elif init_from_hf:
            body["init_from"] = {"hf_repo_id": init_from_hf}
        run_create = RunCreate.from_dict(body)
        report = api.preflight(run_create).to_dict()
        _print_preflight(report, quiet=as_json)
        if preflight_only:
            if as_json:
                _print_json(report)
            raise typer.Exit(0 if report["ok"] else 1)
        if not report["ok"]:
            raise fail("preflight failed; fix the errors above")
        run = api.create_run(run_create, idempotency_key=f"train-{secrets.token_hex(16)}").to_dict()
        if as_json:
            _print_json(run)
        else:
            out.print(
                f"[green]Run #{run['number']}[/] {esc(run['name'])} queued "
                f"(id {esc(run['id'])}, dataset {esc(ds['name'])} v{ver['version']}, "
                f"policy {esc(policy)})"
            )
            out.print(f"Follow with: hibiscus logs -f {esc(run['id'])}")
        if follow:
            code = _follow_logs(api, str(run["id"]), tail=0, show_metrics=False)
            raise typer.Exit(code)


def _print_preflight(report: dict[str, Any], quiet: bool) -> None:
    con = err
    for c in report.get("checks", []):
        sev = c.get("severity")
        color = {"error": "red", "warning": "yellow"}.get(str(sev), "dim")
        if quiet and sev not in ("error", "warning"):
            continue
        con.print(
            f"[{color}]{sev:>7}[/] {esc(c.get('id'))}: {esc(c.get('message'))} " + esc(f"[{c.get('code')}]")
        )
    est = report.get("estimate") or {}
    res = report.get("resolved") or {}
    if not quiet:
        bits = []
        if res.get("gpu_id"):
            bits.append(f"gpu {res['gpu_id']}")
        if res.get("mixed_precision"):
            bits.append(f"precision {res['mixed_precision']}")
        if est.get("peak_vram_mb"):
            bits.append(f"~{est['peak_vram_mb']} MB VRAM")
        if est.get("total_duration_s"):
            bits.append(f"~{est['total_duration_s'] / 3600:.1f} h ({est.get('source')})")
        if bits:
            con.print("[dim]estimate: " + esc(", ".join(bits)))


# ====================================================================================== runs / logs
@runs_app.command("ls")
def runs_ls(
    status: list[str] = typer.Option([], "--status", help="Filter (repeatable): queued, running, …"),
    mine: bool = typer.Option(False, "--mine", help="Only my runs"),
    q: str | None = typer.Option(None, "--q"),
    limit: int = typer.Option(50, "--limit", min=1, max=200),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """List runs, newest first."""
    with handle_errors(), _api() as api:
        page = api.list_runs(
            status=status or None, created_by="me" if mine else None, q=q, limit=limit
        ).to_dict()
    if as_json:
        _print_json(page)
        return
    t = SafeTable("#", "name", "status", "policy", "dataset", "progress", "gpu", "loss", "created", "id")
    for r in page["items"]:
        p = r.get("progress") or {}
        cur, tot = p.get("current_step", 0), p.get("total_steps", 0)
        pct = f"{cur}/{tot}" + (f" ({100 * cur / tot:.0f}%)" if tot else "")
        loss = (r.get("latest_metrics") or {}).get("loss")
        t.add_row(
            str(r["number"]),
            r["name"],
            r["status"],
            r["policy_type"],
            f"{r['dataset']['name']} v{r['dataset']['version']}",
            pct,
            str(r.get("gpu_id") or "-"),
            f"{loss:.4g}" if isinstance(loss, (int, float)) else "-",
            _short(r.get("created_at")),
            str(r["id"]),
        )
    out.print(t)


@runs_app.command("show")
def runs_show(
    ref: str = typer.Argument(..., help="Run id or #number"), as_json: bool = typer.Option(False, "--json")
) -> None:
    """Show one run."""
    with handle_errors(), _api() as api:
        run = api.get_run(resolve_run_id(api, ref)).to_dict()
    if as_json:
        _print_json(run)
        return
    p = run.get("progress") or {}
    out.print(f"[bold]#{run['number']} {esc(run['name'])}[/]  {esc(run['status'])}  ({esc(run['id'])})")
    out.print(
        f"policy {esc(run['policy_type'])}  "
        f"dataset {esc(run['dataset']['name'])} v{run['dataset']['version']}"
        f"  gpu {esc(run.get('gpu_id') or run.get('requested_gpu') or '-')}"
    )
    out.print(f"step {p.get('current_step')}/{p.get('total_steps')}  eta {esc(p.get('eta_s') or '-')} s")
    if run.get("error_code"):
        out.print(f"[red]error {esc(run['error_code'])}: {esc(run.get('error_message') or '')}")
    if run.get("model_id"):
        out.print(f"model {esc(run['model_id'])}  (hibiscus pull {esc(run['model_id'])} --to ./models)")


def _follow_logs(api: HibiscusApi, run_id: str, *, tail: int | None, show_metrics: bool) -> int:
    def line(s: str) -> None:
        out.out(s, highlight=False)

    def event(kind: str, text: str) -> None:
        color = {
            "error": "red",
            "warning": "yellow",
            "status": "cyan",
            "end": "bold",
            "reconnect": "dim",
        }.get(kind, "")
        err.print(f"[{color}]» {esc(text)}[/]" if color else f"» {esc(text)}")

    follower = LogFollower(api, run_id, LogSink(line=line, event=event), show_metrics=show_metrics)
    follower.print_existing(tail)
    final = follower.follow()
    return 0 if final == "succeeded" else 1


@app.command()
def logs(
    ref: str = typer.Argument(..., help="Run id or #number"),
    follow_: bool = typer.Option(False, "--follow", "-f", help="Stream live (reconnects automatically)"),
    tail: int | None = typer.Option(None, "--tail", "-n", min=0, help="Only print the last N stored lines"),
    metrics: bool = typer.Option(False, "--metrics", help="Also print metric events while following"),
) -> None:
    """Print a run's log; with -f follow it live until the run ends (exit 0 = succeeded)."""
    with handle_errors(), _api() as api:
        run_id = resolve_run_id(api, ref)
        if not follow_:
            follower = LogFollower(
                api, run_id, LogSink(line=lambda s: out.out(s, highlight=False), event=lambda k, t: None)
            )
            follower.print_existing(tail)
            return
        code = _follow_logs(api, run_id, tail=tail, show_metrics=metrics)
    raise typer.Exit(code)


# ====================================================================================== models / pull
@models_app.command("ls")
def models_ls(
    q: str | None = typer.Option(None, "--q"),
    limit: int = typer.Option(50, "--limit", min=1, max=200),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """List exported models (bundles)."""
    with handle_errors(), _api() as api:
        page = api.list_models(q=q, limit=limit).to_dict()
    if as_json:
        _print_json(page)
        return
    t = SafeTable("name", "policy", "run", "step", "status", "verified", "onnx", "size", "id")
    for m in page["items"]:
        t.add_row(
            m["name"],
            m["policy_type"],
            f"#{m['run_number']}",
            str(m["step"]),
            m["status"],
            "yes" if m.get("verified") else "no",
            m["onnx_status"],
            _human(m.get("bundle_size_bytes")),
            str(m["id"]),
        )
    out.print(t)


@app.command()
def pull(
    model: str = typer.Argument(..., help="Model id or name"),
    to: Path = typer.Option(Path("."), "--to", help="Destination directory"),
    only: str | None = typer.Option(
        None, "--only", help="Fetch only files under this bundle path (e.g. pretrained_model)"
    ),
    force: bool = typer.Option(False, "--force", help="Re-download even if a verified copy exists"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Download a model bundle and verify every file against MANIFEST.json."""
    with handle_errors(), _api() as api, _make_progress() as progress:
        task: dict[str, TaskID] = {}

        def start(total: int, have: int) -> None:
            if "t" not in task:
                task["t"] = progress.add_task("downloading", total=total or None, completed=have)

        events = PullEvents(
            on_start=start,
            on_bytes=lambda n: progress.advance(task["t"], n) if "t" in task else None,
            on_info=lambda m: progress.console.print(f"[dim]{esc(m)}"),
        )
        res = Puller(api, events).pull(resolve_model_id(api, model), to, only=only, force=force)
    if as_json:
        _print_json({**res.__dict__, "bundle_dir": str(res.bundle_dir)})
        return
    state = "already present, verified" if res.skipped else "verified"
    out.print(
        f"[green]{esc(res.bundle_name)}[/] -> {esc(res.bundle_dir)} ({res.files_verified} files {esc(state)})"
    )
    if (res.bundle_dir / "pretrained_model").is_dir():
        out.print(f"Use with LeRobot: --policy.path={esc(res.bundle_dir / 'pretrained_model')}")
    if (res.bundle_dir / "run_on_robot.sh").is_file():
        out.print(f"Run on the robot (LeLab venv): {esc(res.bundle_dir / 'run_on_robot.sh')}")


# ====================================================================================== station
STATION_BIN = "hibiscus-station"


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True, "help_option_names": []},
)
def station(ctx: typer.Context) -> None:
    """Launch Hibiscus Station (the local robot app); every argument is passed to `hibiscus-station`.

    Examples: `hibiscus station --mock`, `hibiscus station url`, `hibiscus station --help`.
    """
    exe = shutil.which(STATION_BIN)
    if exe is None:
        err.print(f"[bold red]error:[/] `{STATION_BIN}` is not installed (or not on PATH).")
        err.print(
            "[yellow]hint:[/] install it with `uv tool install hibiscus-station`, "
            "or run it once without installing: `uvx hibiscus-station`"
        )
        raise typer.Exit(1)
    os.execvp(exe, [STATION_BIN, *ctx.args])  # noqa: S606 - argv list, no shell


def run() -> None:  # pragma: no cover - console entry convenience
    app()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
