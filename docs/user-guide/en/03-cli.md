# 3. The `hibiscus` CLI on the collection machine

*Primary (Vietnamese) version: `../vi/03-cli-may-collect.md`.*

The collection machine ("machine B") is the PC connected to the robot where you record with LeLab
or `lerobot-record`. The syntax below follows the design (PLAN §3.7); `hibiscus --help` on your
installed version is authoritative.

## 3.1 Install

Install it as a standalone tool, **not** into the LeLab venv. The CLI is **not on PyPI**: do not
run `uv tool install hibiscus` / `pipx install hibiscus` (that may install an unrelated package).
Install the `.whl` your admin gives you, or from source:

```bash
uv tool install https://github.com/Bigkatoan/Hibiscus/releases/latest/download/hibiscus-0.1.1-py3-none-any.whl   # or: pipx install <wheel>
cd Hibiscus/cli && uv tool install .                  # from a source checkout
hibiscus --version
```

On machines with ROS in `PYTHONPATH`, run `env -u PYTHONPATH hibiscus …` if you see odd import errors.

## 3.2 Sign in with a personal access token

Web: **Account › Access tokens › Create token**, name it after the machine, workspace, permissions
**Collection machine**, 90 days. **Copy it now** — it is shown once. Then:

```bash
hibiscus login --server https://robot.example.com    # paste hbp_... when asked (hidden)
```

The token dialog on the web shows this command ready to copy. Do **not** use
`hibiscus login --token hbp_...`: the token would stay in your shell history.

A token works in **one** workspace. Lost machine or leaked token: revoke it on the web immediately.

## 3.3 Push a dataset

```bash
hibiscus push ~/.cache/huggingface/lerobot/<user>/so101_picknplace --name so101_picknplace     # new dataset
hibiscus push ~/.cache/huggingface/lerobot/<user>/so101_picknplace --dataset so101_picknplace  # new version
hibiscus push ~/Picknplace_20261114_221710.rar --name so101_picknplace                         # an archive
hibiscus watch ~/.cache/huggingface/lerobot/<user>    # push every new recording automatically
```

Progress bar; resumes after network drops (re-running the command continues). The server
validates the dataset after the upload. By default the command returns as soon as the upload is
done (exit code 0) and prints the version and validation job ids. Add `--wait` to wait for
validation: it prints `Validation result: ready` (or `invalid` / `failed`) and **exits 1** when
the dataset is Invalid. The individual checks, failing episodes and fixes are on the dataset page
on the web, or `hibiscus datasets show <name>`.

## 3.4 Train and follow

```bash
hibiscus train --dataset so101_picknplace --policy act --preset standard
hibiscus logs -f 42
```

## 3.5 Pull a model

```bash
hibiscus pull so101_picknplace_act-r42-step100000 --to ~/lelab/models
hibiscus pull so101_picknplace_act-r42-step100000 --only pretrained_model --to ~/lelab/models
```

Resumable; SHA-256 verified. Then see chapter 6.

## 3.6 Common CLI errors

The CLI prints `error: …` (the server error code), usually followed by a `hint: …` line:

| CLI output (`error:` / `hint:`) | Fix |
|---|---|
| `token_revoked` / `token_expired` | Create a new token, `hibiscus login` again |
| `unauthenticated` / `not logged in to …` | `hibiscus login --server …` |
| `insufficient_scope` (the hint lists the scope each command needs) | Create a token with the **Collection machine** preset |
| `forbidden` (e.g. token of another workspace) | Create a token for the right workspace |
| `quota_exceeded` | Delete unused versions/models or ask an admin |
| `preflight_failed` | Read the checks printed above; try `hibiscus train … --preflight-only` |
| `model_not_ready` | The bundle is still building; retry later |
| `dataset_version_not_ready` | `hibiscus datasets show <name>` |
| `network error: …` | Re-run the same command: uploads and downloads resume |

Parts corrupted in transit are resent automatically; check Wi-Fi/cable if it repeats.
