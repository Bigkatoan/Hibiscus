"""Artifact reads for logs / bundles: ``app.core.storage.S3`` plus prefix listing and ranged reads."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from botocore.exceptions import ClientError

from app.core.settings import Settings
from app.core.storage import S3


@dataclass(frozen=True, slots=True)
class ObjectInfo:
    key: str
    size: int
    etag: str


class AsyncStore(S3):
    @classmethod
    def from_settings(cls, s: Settings) -> AsyncStore:
        return cls(s.s3_endpoint_url, s.s3_access_key, s.s3_secret_key, s.s3_region)

    async def head(self, bucket: str, key: str) -> ObjectInfo | None:
        async with self.client() as s3:
            try:
                r = await s3.head_object(Bucket=bucket, Key=key)
            except ClientError:
                return None
            return ObjectInfo(key, int(r["ContentLength"]), str(r.get("ETag", "")).strip('"'))

    async def list_prefix(self, bucket: str, prefix: str) -> list[ObjectInfo]:
        out: list[ObjectInfo] = []
        async with self.client() as s3:
            paginator = s3.get_paginator("list_objects_v2")
            async for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                for o in page.get("Contents", []):
                    out.append(
                        ObjectInfo(o.get("Key", ""), int(o.get("Size", 0)), str(o.get("ETag", "")).strip('"'))
                    )
        return out

    async def get_bytes(self, bucket: str, key: str, start: int = 0, end: int | None = None) -> bytes:
        rng = f"bytes={start}-" + ("" if end is None else str(end))
        async with self.client() as s3:
            r = await s3.get_object(Bucket=bucket, Key=key, Range=rng)
            body = r["Body"]
            try:
                data: bytes = await body.read()
            finally:
                body.close()
            return data

    async def stream(
        self, bucket: str, key: str, start: int = 0, end: int | None = None, chunk: int = 1 << 20
    ) -> AsyncIterator[bytes]:
        rng = f"bytes={start}-" + ("" if end is None else str(end))
        async with self.client() as s3:
            r = await s3.get_object(Bucket=bucket, Key=key, Range=rng)
            body = r["Body"]
            try:
                while data := await body.read(chunk):
                    yield data
            finally:
                body.close()


def parse_s3_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("s3://"):
        raise ValueError(uri)
    bucket, _, key = uri[5:].partition("/")
    return bucket, key
