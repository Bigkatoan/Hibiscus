"""End-to-end CLI tests: Typer commands against the OpenAPI-validated fake server."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from hibiscus.main import app
from tests.fake_server import TOKEN, FakeHibiscus, SseConnection, now
from tests.test_pull import BUNDLE, _files
from tests.test_watch import make_recording

SERVER = "https://hibiscus.test"


@pytest.fixture
def runner(monkeypatch: pytest.MonkeyPatch) -> CliRunner:
    monkeypatch.setenv("COLUMNS", "250")
    return CliRunner()


@pytest.fixture
def logged_in(fake: FakeHibiscus, runner: CliRunner) -> FakeHibiscus:
    res = runner.invoke(app, ["login", "--server", SERVER, "--token", TOKEN])
    assert res.exit_code == 0, res.output
    return fake


def test_login_whoami_logout(fake: FakeHibiscus, runner: CliRunner, isolated_dirs: Path) -> None:
    res = runner.invoke(app, ["login", "--server", SERVER], input=TOKEN + "\n")
    assert res.exit_code == 0, res.output
    assert "Logged in" in res.output and "workspace Lab" in res.output
    cfg = json.loads((isolated_dirs / "config" / "config.json").read_text())
    assert cfg["server"] == SERVER + "/api/v1" and cfg["workspace_id"] == fake.workspace_id
    assert TOKEN not in (isolated_dirs / "config" / "config.json").read_text()  # secret only in the store
    cred = isolated_dirs / "config" / "credentials.json"
    assert cred.stat().st_mode & 0o777 == 0o600
    res = runner.invoke(app, ["whoami"])
    assert res.exit_code == 0 and "Collector" in res.output and "datasets:write" in res.output
    assert TOKEN not in res.output
    res = runner.invoke(app, ["logout"])
    assert res.exit_code == 0 and "Logged out" in res.output
    res = runner.invoke(app, ["whoami"])
    assert res.exit_code == 1 and "not logged in" in res.output


def test_login_rejects_bad_token(fake: FakeHibiscus, runner: CliRunner) -> None:
    res = runner.invoke(app, ["login", "--server", SERVER, "--token", "nope"])
    assert res.exit_code == 1 and "does not look like" in res.output
    res = runner.invoke(app, ["login", "--server", SERVER, "--token", "hbp_ZZZZZZZZ_" + "z" * 43])
    assert res.exit_code == 1 and "unauthenticated" in res.output and "hibiscus login" in res.output


def test_datasets_ls_and_show(logged_in: FakeHibiscus, runner: CliRunner) -> None:
    logged_in.add_dataset("so101_picknplace", versions=2)
    res = runner.invoke(app, ["datasets", "ls"])
    assert res.exit_code == 0, res.output
    assert "so101_picknplace" in res.output and "v2" in res.output
    res = runner.invoke(app, ["datasets", "show", "so101_picknplace", "--version", "1"])
    assert res.exit_code == 0, res.output
    assert "v1: robot_type=so_follower" in res.output and "observation.images.wrist_cam" in res.output
    res = runner.invoke(app, ["datasets", "show", "so101_picknplace", "--json"])
    data = json.loads(res.output)
    assert data["version_detail"]["version"] == 2 and len(data["versions"]) == 2
    res = runner.invoke(app, ["datasets", "show", "missing"])
    assert res.exit_code == 1 and "no dataset named" in res.output


def test_push_dir_and_wait(logged_in: FakeHibiscus, runner: CliRunner, tmp_path: Path) -> None:
    rec = make_recording(tmp_path / "my_rec")
    res = runner.invoke(app, ["push", str(rec), "--json"])
    assert res.exit_code == 0, res.output
    out = json.loads(res.output[res.output.index("{") :])
    s = logged_in.uploads[out["upload_id"]]
    assert (
        s["filename"] == "my_rec.tar" and s["archive_format"] == "tar" and s["new_dataset_name"] == "my_rec"
    )
    assert s["assembled_sha256"] == s["sha256"]
    # second push of the same dataset as a new version, waiting for validation
    v_id = None

    def mark_ready() -> None:
        for v in logged_in.versions.values():
            v["status"] = "ready"

    logged_in.faults.clear()
    (rec / "meta" / "stats.json").write_text('{"x": 1}')
    res = runner.invoke(app, ["push", str(rec), "--dataset", "my_rec"])
    assert res.exit_code == 0, res.output
    assert "dataset my_rec v2" in res.output
    mark_ready()
    v_id = next(v["id"] for v in logged_in.versions.values() if v["version"] == 2)
    assert v_id


def test_push_archive_name_and_conflicting_flags(
    logged_in: FakeHibiscus, runner: CliRunner, tmp_path: Path
) -> None:
    arch = tmp_path / "Picknplace_2026.rar"
    arch.write_bytes(os.urandom(3000))
    res = runner.invoke(app, ["push", str(arch), "--name", "x", "--dataset", "y"])
    assert res.exit_code == 1 and "either --dataset" in res.output
    res = runner.invoke(app, ["push", str(arch)])
    assert res.exit_code == 0, res.output
    (s,) = logged_in.uploads.values()
    assert s["new_dataset_name"] == "Picknplace_2026" and s["archive_format"] == "rar"
    res = runner.invoke(app, ["push", str(arch)])  # same name again -> contract error code surfaced
    assert res.exit_code == 1 and "dataset_name_taken" in res.output


def test_watch_once(logged_in: FakeHibiscus, runner: CliRunner, tmp_path: Path) -> None:
    root = tmp_path / "recs"
    make_recording(root / "sess_a")
    make_recording(root / "sess_b")
    (root / "sess_b" / "data" / "chunk-000" / "file-000.parquet").write_bytes(b"PAR1partial")
    res = runner.invoke(app, ["watch", str(root), "--once", "--debounce", "0", "--interval", "1"])
    assert res.exit_code == 0, res.output
    names = sorted(s["new_dataset_name"] for s in logged_in.uploads.values())
    assert names == ["sess_a"]
    assert "not finalized" in res.output
    res = runner.invoke(app, ["watch", str(root), "--once", "--debounce", "0", "--interval", "1"])
    assert len(logged_in.uploads) == 1  # ledger: not uploaded twice


def test_train_with_overrides_and_follow(logged_in: FakeHibiscus, runner: CliRunner) -> None:
    ds = logged_in.add_dataset("so101_picknplace")
    res = runner.invoke(
        app,
        [
            "train",
            "--dataset",
            "so101_picknplace",
            "--policy",
            "act",
            "--preset",
            "quick",
            "--set",
            "steps=300",
            "--set",
            "chunk_size=50",
            "--set",
            "policy.use_vae=false",
            "--gpu",
            "cuda0",
            "--heldout",
            "0.1",
            "--seed",
            "7",
        ],
    )
    assert res.exit_code == 0, res.output
    body = logged_in.last_create
    assert body["config"] == {"policy": {"chunk_size": 50, "use_vae": False}, "train": {"steps": 300}}
    assert body["preset"] == "quick" and body["gpu"] == "cuda0" and body["seed"] == 7
    assert body["dataset_version_id"] == ds["latest_version"]["id"]
    assert logged_in.last_preflight == body
    assert "Run #1" in res.output
    idem = [r.headers.get("idempotency-key") for r in logged_in.requests if r.operation_id == "createRun"]
    assert idem[0] and idem[0].startswith("train-")

    res = runner.invoke(app, ["train", "-d", "so101_picknplace", "-p", "act", "--set", "bogus=1"])
    assert res.exit_code == 1 and "unknown option 'bogus'" in res.output

    logged_in.preflight_ok = False
    res = runner.invoke(app, ["train", "-d", "so101_picknplace", "-p", "act"])
    assert res.exit_code == 1 and "gpu_insufficient_vram" in res.output and "preflight failed" in res.output
    assert len(logged_in.runs) == 1


def test_runs_ls_and_logs(logged_in: FakeHibiscus, runner: CliRunner) -> None:
    run = logged_in.add_run(number=42, status="running", log=b"step 1\nstep 2\n")
    rid = run["id"]
    res = runner.invoke(app, ["runs", "ls"])
    assert res.exit_code == 0 and "42" in res.output and "running" in res.output
    res = runner.invoke(app, ["runs", "show", "#42"])
    assert res.exit_code == 0 and "#42" in res.output
    res = runner.invoke(app, ["logs", "#42"])
    assert res.exit_code == 0 and res.output.splitlines() == ["step 1", "step 2"]
    logged_in.runs[rid]["status"] = "succeeded"
    logged_in.sse_scripts[rid] = [
        SseConnection(
            live=[
                ("log", {"kind": "log", "byte_offset": 14, "lines": ["step 3"]}, False),
                (
                    "status",
                    {"kind": "status", "run_id": rid, "from": "running", "to": "succeeded", "ts": now()},
                    True,
                ),
            ],
            end=True,
        )
    ]
    res = runner.invoke(app, ["logs", "-f", rid, "--tail", "1"])
    assert res.exit_code == 0, res.output
    assert "step 2" in res.output and "step 3" in res.output and "step 1" not in res.output
    assert "running -> succeeded" in res.output
    logged_in.runs[rid]["status"] = "failed"
    res = runner.invoke(app, ["logs", "-f", rid, "-n", "0"])
    assert res.exit_code == 1 and "run finished: failed" in res.output
    res = runner.invoke(app, ["logs", "#999"])
    assert res.exit_code == 1 and "run #999 not found" in res.output


def test_models_ls_and_pull(logged_in: FakeHibiscus, runner: CliRunner, tmp_path: Path) -> None:
    model = logged_in.add_model(_files(), bundle_name=BUNDLE)
    res = runner.invoke(app, ["models", "ls"])
    assert res.exit_code == 0 and model["name"] in res.output
    res = runner.invoke(app, ["pull", model["name"], "--to", str(tmp_path / "m")])
    assert res.exit_code == 0, res.output
    assert f"--policy.path={tmp_path / 'm' / BUNDLE / 'pretrained_model'}" in res.output.replace("\n", "")
    res = runner.invoke(app, ["pull", model["id"], "--to", str(tmp_path / "m"), "--json"])
    assert json.loads(res.output[res.output.index("{") :])["skipped"] is True


def test_version_flag(runner: CliRunner) -> None:
    res = runner.invoke(app, ["--version"])
    assert res.exit_code == 0 and "hibiscus 0.1.1" in res.output


def test_server_text_is_not_rich_markup(logged_in: FakeHibiscus, runner: CliRunner) -> None:
    logged_in.add_dataset("[bold red]evil[/] [link=file:///etc]x")
    res = runner.invoke(app, ["datasets", "ls"])
    assert res.exit_code == 0, res.output
    assert "[bold red]evil[/]" in res.output and "[link=file:///etc]x" in res.output


def test_station_execs_hibiscus_station_with_passthrough_args(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hibiscus.main as main_mod

    calls: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(main_mod.shutil, "which", lambda name: f"/opt/bin/{name}")
    monkeypatch.setattr(main_mod.os, "execvp", lambda file, args: calls.append((file, list(args))))
    for argv in (["--mock", "--no-browser"], ["url"], ["--help"], []):
        r = runner.invoke(app, ["station", *argv])
        assert r.exit_code == 0, r.output
    assert calls == [
        ("/opt/bin/hibiscus-station", ["hibiscus-station", "--mock", "--no-browser"]),
        ("/opt/bin/hibiscus-station", ["hibiscus-station", "url"]),
        ("/opt/bin/hibiscus-station", ["hibiscus-station", "--help"]),
        ("/opt/bin/hibiscus-station", ["hibiscus-station"]),
    ]


def test_station_not_installed(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    import hibiscus.main as main_mod

    monkeypatch.setattr(main_mod.shutil, "which", lambda name: None)
    monkeypatch.setattr(main_mod.os, "execvp", lambda *a: pytest.fail("must not exec"))
    r = runner.invoke(app, ["station", "--mock"])
    assert r.exit_code == 1
    assert "github.com/Bigkatoan/hibiscus-station" in r.output


def test_json_output_is_plain(
    logged_in: FakeHibiscus, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--json`` must stay parseable when colour is forced (FORCE_COLOR=1 in CI, a TTY, ...)."""
    from rich.console import Console

    import hibiscus.main as main

    monkeypatch.setattr(main, "out", Console(force_terminal=True, color_system="truecolor"))
    logged_in.add_dataset("so101_picknplace", versions=1)
    res = runner.invoke(app, ["datasets", "show", "so101_picknplace", "--json"])
    assert res.exit_code == 0, res.output
    assert "\x1b[" not in res.output
    assert json.loads(res.output)["dataset"]["name"] == "so101_picknplace"
