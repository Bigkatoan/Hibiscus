# 2. Datasets: upload, validation, preview

*Primary (Vietnamese) version: `../vi/02-dataset.md`.*

## 2.1 What Hibiscus accepts

* **LeRobot v3.0** datasets (LeRobot 0.7.1 / LeLab default); **v2.1** is converted automatically.
* One dataset = a folder with `meta/` (`info.json`, `stats.json`, `tasks.parquet`, `episodes/`),
  `data/`, `videos/` — usually `~/.cache/huggingface/lerobot/<user>/<dataset>`.
* Browser: **one archive** `.zip`, `.tar`, `.tar.gz`, `.tar.zst` or `.rar` (RAR5, including files
  p7zip cannot open). A whole **folder**: use `hibiscus push` (chapter 3). One dataset per archive.

## 2.2 Upload in the browser

**Datasets › Upload dataset** → choose/drop the file → *New dataset* (name) or *New version of an
existing dataset* → **Upload**. The browser fingerprints the file (SHA-256), then sends parts of
≤ 64 MiB. Network drops pause and resume automatically; if you closed the tab, open the upload page
again and choose **the same file** to continue. Once uploaded you can leave: unpacking and
validation run in the background and you get a 🔔 notification.

## 2.3 Validation

Status: *Waiting → Unpacking → Validating → Ready* (or *Invalid*; *Processing failed* = server
problem → **Validate again**). Seven steps: file integrity, unpack (safe paths, no links, no
compression bombs), folder structure, features and joints, video decoding (first/middle/last frame
of **every** episode), timestamps, statistics.

* **Errors** block training and say which episode/file and what to do.
* **Warnings** don't block — but read them (e.g. irregular timestamps = dropped frames).
* Fixed the data? Upload it as a **new version**; versions are immutable.

| Message | Usual cause | Fix |
|---|---|---|
| No LeRobot dataset found in the archive | Archived the parent folder or only `videos/` | Archive the folder that contains `meta/` |
| A video frame could not be decoded | Recording stopped abruptly, truncated video | Remove the episode (`lerobot-edit-dataset`) or re-record |
| The data contains missing numbers (NaN) | Motor/sensor read failure | Remove/re-record that episode |
| The archive contains symbolic links | Archiver kept links | `tar --dereference -cf ds.tar <folder>` |

## 2.4 Preview

**Overview** (format, robot type, fps, cameras, joint names, counts, tasks, fingerprint) and
**Episodes** (thumbnails, length distribution; episode page with video synced to per-joint
state/action plots; ←/→ to switch episodes). Web video is a **low-quality H.264 preview** so any
browser can play it; the original (e.g. AV1) is untouched and used for training.

## 2.5 Hugging Face import and merge

* **Import from Hugging Face**: `hf://<org>/<repo>[@<revision>]`; private repos need your stored
  Hugging Face token (Account settings).
* **Merge datasets**: several *Ready* versions with **identical** features (cameras, joints, fps)
  → one new validated version.

## 2.6 Delete

A dataset/version used by an unfinished run cannot be deleted. Existing runs and models keep
working after a dataset is deleted.
