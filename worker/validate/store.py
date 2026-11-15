"""S3 (MinIO) access for the validate worker. Local adapter until A4's ``worker/core`` S3 helper.

Object layout (ADR-0004, docs/handoff/A3-data.md):

* upload object:  ``s3://hibiscus-uploads/<workspace_id>/uploads/<upload_id>/<filename>``
* dataset files:  ``s3://hibiscus-datasets/<workspace_id>/<dataset_id>/<version_id>/<relpath>``
  (exactly the LeRobot dataset root; this is what GPU workers download to /cache/datasets/<id>/)
* derived files:  ``s3://hibiscus-datasets/<workspace_id>/<dataset_id>/<version_id>.derived/``
  ``previews/<cam>/episode_XXXXXX.{mp4,jpg}``, ``episodes/episode_XXXXXX.json``, ``manifest.json``
"""

from __future__ import annotations

import json
import mimetypes
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.config import Config

from validate.hashing import FileEntry

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

TRANSFER = TransferConfig(
    multipart_threshold=64 * 1024 * 1024, multipart_chunksize=64 * 1024 * 1024, max_concurrency=4
)
CONTENT_TYPES = {
    ".mp4": "video/mp4",
    ".jpg": "image/jpeg",
    ".json": "application/json",
    ".parquet": "application/octet-stream",
}


def dataset_prefix(workspace_id: str, dataset_id: str, version_id: str) -> str:
    return f"{workspace_id}/{dataset_id}/{version_id}/"


def derived_prefix(workspace_id: str, dataset_id: str, version_id: str) -> str:
    return f"{workspace_id}/{dataset_id}/{version_id}.derived/"


def content_type(path: str) -> str:
    ext = Path(path).suffix.lower()
    return CONTENT_TYPES.get(ext) or mimetypes.guess_type(path)[0] or "application/octet-stream"


class Store:
    def __init__(
        self, endpoint_url: str, access_key: str, secret_key: str, region: str = "us-east-1"
    ) -> None:
        self.client: S3Client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(
                signature_version="s3v4", s3={"addressing_style": "path"}, retries={"max_attempts": 5}
            ),
        )

    def download(
        self, bucket: str, key: str, dest: Path, progress: Callable[[int], None] | None = None
    ) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        self.client.download_file(bucket, key, str(dest), Callback=progress, Config=TRANSFER)

    def upload_file(self, local: Path, bucket: str, key: str) -> None:
        self.client.upload_file(
            str(local), bucket, key, ExtraArgs={"ContentType": content_type(key)}, Config=TRANSFER
        )

    def put_json(self, bucket: str, key: str, data: Any) -> None:
        self.client.put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps(data, separators=(",", ":")).encode(),
            ContentType="application/json",
        )

    def get_json(self, bucket: str, key: str) -> Any:
        obj = self.client.get_object(Bucket=bucket, Key=key)
        return json.loads(obj["Body"].read())

    def exists(self, bucket: str, key: str) -> bool:
        try:
            self.client.head_object(Bucket=bucket, Key=key)
        except self.client.exceptions.ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return False
            raise
        return True

    def upload_tree(
        self,
        root: Path,
        bucket: str,
        prefix: str,
        files: list[FileEntry] | None = None,
        progress: Callable[[int], None] | None = None,
    ) -> int:
        """Upload ``root`` below ``prefix``; returns bytes uploaded."""
        rels = (
            [f.path for f in files]
            if files is not None
            else sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
        )
        total = 0
        for rel in rels:
            p = root / rel
            self.upload_file(p, bucket, prefix + rel)
            total += p.stat().st_size
            if progress is not None:
                progress(p.stat().st_size)
        return total

    def download_tree(self, bucket: str, prefix: str, files: list[str], dest: Path) -> None:
        for rel in files:
            if rel.startswith("/") or ".." in rel.split("/"):
                raise ValueError(f"unsafe manifest path {rel!r}")
            self.download(bucket, prefix + rel, dest / rel)

    def delete_prefix(self, bucket: str, prefix: str) -> int:
        n = 0
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            keys = [{"Key": o["Key"]} for o in page.get("Contents", []) if "Key" in o]
            if keys:
                self.client.delete_objects(Bucket=bucket, Delete={"Objects": keys, "Quiet": True})  # type: ignore[typeddict-item]  # stub requires full ObjectIdentifier
                n += len(keys)
        return n
