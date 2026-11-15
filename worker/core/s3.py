"""S3/MinIO helpers for workers (boto3, sync).

Public API (stable for A3/A5):
    * :class:`StorageError` - raised after ``max_retries`` failed attempts (maps to run error
      ``storage_error``).
    * :class:`ObjectStore` - ``upload_file``, ``upload_dir``, ``download_file``, ``download_prefix``,
      ``list_prefix``, ``delete_prefix``, ``put_bytes``, ``get_bytes``, ``exists``.
    * :func:`parse_s3_uri` - ``s3://bucket/key`` -> ``(bucket, key)``.
"""

from __future__ import annotations

import functools
import logging
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

log = logging.getLogger(__name__)
T = TypeVar("T")


class StorageError(RuntimeError):
    """Object storage failed after retries."""


def parse_s3_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("s3://"):
        raise ValueError(f"not an s3 uri: {uri!r}")
    bucket, _, key = uri[5:].partition("/")
    if not bucket:
        raise ValueError(f"missing bucket in {uri!r}")
    return bucket, key


@dataclass(frozen=True, slots=True)
class S3Object:
    key: str
    size: int


class ObjectStore:
    def __init__(
        self,
        *,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
        max_retries: int = 5,
    ) -> None:
        self.max_retries = max_retries
        self.client: S3Client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(
                s3={"addressing_style": "path"},
                retries={"max_attempts": 2, "mode": "standard"},
                signature_version="s3v4",
            ),
        )

    # -- retry wrapper ---------------------------------------------------------------------------
    def _retry(self, what: str, fn: Callable[[], T]) -> T:
        delay = 0.5
        for attempt in range(1, self.max_retries + 1):
            try:
                return fn()
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code", "")
                if code in {"NoSuchKey", "404", "NoSuchBucket", "AccessDenied"}:
                    raise StorageError(f"{what}: {code}") from exc
                last: Exception = exc
            except (BotoCoreError, OSError) as exc:
                last = exc
            if attempt < self.max_retries:
                log.warning("s3 %s failed (attempt %d): %s", what, attempt, type(last).__name__)
                time.sleep(delay)
                delay = min(delay * 2, 8.0)
        raise StorageError(f"{what} failed after {self.max_retries} attempts: {last}") from last

    # -- buckets ---------------------------------------------------------------------------------
    def ensure_bucket(self, bucket: str) -> None:
        try:
            self.client.head_bucket(Bucket=bucket)
        except ClientError:
            self.client.create_bucket(Bucket=bucket)

    # -- objects ---------------------------------------------------------------------------------
    def upload_file(self, path: Path, bucket: str, key: str) -> int:
        size = path.stat().st_size
        self._retry(f"upload {key}", lambda: self.client.upload_file(str(path), bucket, key))
        return size

    def upload_dir(self, root: Path, bucket: str, prefix: str) -> int:
        """Upload every regular file under ``root`` to ``prefix/<relative path>``; returns bytes."""
        total = 0
        prefix = prefix.rstrip("/")
        for path in sorted(p for p in root.rglob("*") if p.is_file() and not p.is_symlink()):
            rel = path.relative_to(root).as_posix()
            total += self.upload_file(path, bucket, f"{prefix}/{rel}")
        return total

    def put_bytes(
        self, data: bytes, bucket: str, key: str, content_type: str = "application/octet-stream"
    ) -> None:
        self._retry(
            f"put {key}",
            lambda: self.client.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type),
        )

    def get_bytes(self, bucket: str, key: str) -> bytes:
        def _get() -> bytes:
            return self.client.get_object(Bucket=bucket, Key=key)["Body"].read()

        return self._retry(f"get {key}", _get)

    def exists(self, bucket: str, key: str) -> bool:
        try:
            self.client.head_object(Bucket=bucket, Key=key)
            return True
        except ClientError:
            return False

    def download_file(self, bucket: str, key: str, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        self._retry(f"download {key}", lambda: self.client.download_file(bucket, key, str(dest)))

    def list_prefix(self, bucket: str, prefix: str) -> Iterator[S3Object]:
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                yield S3Object(key=obj["Key"], size=int(obj["Size"]))

    def download_prefix(self, bucket: str, prefix: str, dest: Path) -> int:
        """Download every object under ``prefix`` into ``dest`` keeping relative paths."""
        prefix = prefix.rstrip("/") + "/"
        total = 0
        objects = self._retry(f"list {prefix}", lambda: list(self.list_prefix(bucket, prefix)))
        for obj in objects:
            rel = obj.key[len(prefix) :]
            if not rel or rel.endswith("/"):
                continue
            target = (dest / rel).resolve()
            if dest.resolve() not in target.parents:
                raise StorageError(f"refusing to write outside {dest}: {obj.key}")
            self.download_file(bucket, obj.key, target)
            total += obj.size
        return total

    def delete_prefix(self, bucket: str, prefix: str) -> int:
        prefix = prefix.rstrip("/") + "/"
        keys = [o.key for o in self.list_prefix(bucket, prefix)]
        for i in range(0, len(keys), 1000):
            chunk = keys[i : i + 1000]
            self._retry(
                f"delete {prefix}",
                functools.partial(
                    self.client.delete_objects,
                    Bucket=bucket,
                    Delete={"Objects": [{"Key": k} for k in chunk], "Quiet": True},
                ),
            )
        return len(keys)
