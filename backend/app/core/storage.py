"""S3 / MinIO wrapper (aioboto3).

Buckets: ``hibiscus-uploads``, ``hibiscus-datasets``, ``hibiscus-artifacts``.

The API never issues presigned URLs (ADR-0010 / CONTRACT_NOTES D1): upload parts stream through
the API (:meth:`S3.put_part`) and downloads stream back (:meth:`S3.stream_object`).
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import aioboto3
from aiobotocore.config import AioConfig
from botocore.exceptions import ClientError

from app.core.errors import ErrorCode, ProblemError

if TYPE_CHECKING:
    from types_aiobotocore_s3.client import S3Client

BUCKET_UPLOADS = "hibiscus-uploads"
BUCKET_DATASETS = "hibiscus-datasets"
BUCKET_ARTIFACTS = "hibiscus-artifacts"
ALL_BUCKETS = (BUCKET_UPLOADS, BUCKET_DATASETS, BUCKET_ARTIFACTS)


@dataclass(frozen=True, slots=True)
class ObjectInfo:
    size: int
    etag: str
    content_type: str | None


@dataclass(frozen=True, slots=True)
class ObjectStream:
    """Body iterator plus metadata. ``start``/``end`` are inclusive byte offsets actually served."""

    body: AsyncIterator[bytes]
    size: int  # full object size
    start: int
    end: int
    etag: str
    content_type: str | None

    @property
    def length(self) -> int:
        return self.end - self.start + 1


class S3:
    def __init__(
        self, endpoint_url: str, access_key: str, secret_key: str, region: str = "us-east-1"
    ) -> None:
        self._session = aioboto3.Session(
            aws_access_key_id=access_key, aws_secret_access_key=secret_key, region_name=region
        )
        self._endpoint = endpoint_url
        self._config = AioConfig(
            signature_version="s3v4", s3={"addressing_style": "path"}, retries={"max_attempts": 3}
        )

    @contextlib.asynccontextmanager
    async def client(self) -> AsyncIterator[S3Client]:
        async with self._session.client("s3", endpoint_url=self._endpoint, config=self._config) as c:
            yield c

    async def ping(self) -> None:
        async with self.client() as c:
            await c.list_buckets()

    async def ensure_buckets(self, names: tuple[str, ...] = ALL_BUCKETS) -> None:
        async with self.client() as c:
            existing = {b["Name"] for b in (await c.list_buckets()).get("Buckets", []) if "Name" in b}
            for n in names:
                if n not in existing:
                    await c.create_bucket(Bucket=n)

    # ---- simple objects ------------------------------------------------------------------------
    async def put_object(self, bucket: str, key: str, body: bytes, content_type: str | None = None) -> str:
        async with self.client() as c:
            extra: dict[str, Any] = {"ContentType": content_type} if content_type else {}
            r = await c.put_object(Bucket=bucket, Key=key, Body=body, **extra)
            return r["ETag"].strip('"')

    async def head_object(self, bucket: str, key: str) -> ObjectInfo | None:
        async with self.client() as c:
            try:
                r = await c.head_object(Bucket=bucket, Key=key)
            except ClientError as e:
                if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                    return None
                raise
            return ObjectInfo(
                size=r["ContentLength"], etag=r["ETag"].strip('"'), content_type=r.get("ContentType")
            )

    async def delete_object(self, bucket: str, key: str) -> None:
        async with self.client() as c:
            await c.delete_object(Bucket=bucket, Key=key)

    async def delete_prefix(self, bucket: str, prefix: str) -> int:
        n = 0
        async with self.client() as c:
            paginator = c.get_paginator("list_objects_v2")
            async for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                objs = [{"Key": o["Key"]} for o in page.get("Contents", []) if "Key" in o]
                if objs:
                    await c.delete_objects(Bucket=bucket, Delete={"Objects": objs})  # type: ignore[typeddict-item]  # list of ObjectIdentifier
                    n += len(objs)
        return n

    async def bucket_size(self, bucket: str, *, max_objects: int = 1_000_000) -> int:
        total = 0
        seen = 0
        async with self.client() as c:
            paginator = c.get_paginator("list_objects_v2")
            async for page in paginator.paginate(Bucket=bucket):
                for o in page.get("Contents", []):
                    total += int(o.get("Size", 0))
                    seen += 1
                if seen >= max_objects:
                    break
        return total

    # ---- multipart (chunked uploads through the API, ADR-0010) -------------------------------
    async def create_multipart(self, bucket: str, key: str, content_type: str | None = None) -> str:
        async with self.client() as c:
            extra: dict[str, Any] = {"ContentType": content_type} if content_type else {}
            r = await c.create_multipart_upload(Bucket=bucket, Key=key, **extra)
            return r["UploadId"]

    async def put_part(self, bucket: str, key: str, upload_id: str, part_number: int, body: bytes) -> str:
        """Upload one part (≤ 64 MiB, already fully read and checksummed by the caller). Returns ETag."""
        async with self.client() as c:
            r = await c.upload_part(
                Bucket=bucket, Key=key, UploadId=upload_id, PartNumber=part_number, Body=body
            )
            return r["ETag"].strip('"')

    async def complete_multipart(
        self, bucket: str, key: str, upload_id: str, parts: list[tuple[int, str]]
    ) -> str:
        """``parts`` = [(part_number, etag), ...]; returns the final object's ETag."""
        async with self.client() as c:
            r = await c.complete_multipart_upload(
                Bucket=bucket,
                Key=key,
                UploadId=upload_id,
                MultipartUpload={"Parts": [{"PartNumber": n, "ETag": f'"{e}"'} for n, e in sorted(parts)]},
            )
            return str(r.get("ETag", "")).strip('"')

    async def abort_multipart(self, bucket: str, key: str, upload_id: str) -> None:
        async with self.client() as c:
            with contextlib.suppress(ClientError):
                await c.abort_multipart_upload(Bucket=bucket, Key=key, UploadId=upload_id)

    # ---- streaming download ------------------------------------------------------------------
    async def stream_object(
        self,
        bucket: str,
        key: str,
        range: tuple[int, int | None] | None = None,
        *,
        chunk_size: int = 1024 * 1024,
    ) -> ObjectStream:
        """Stream an object, optionally a single inclusive byte range ``(start, end|None)``.

        Raises ``ProblemError(404, not_found)`` for a missing key and ``(416,
        range_not_satisfiable)`` for a range outside the object.
        """
        info = await self.head_object(bucket, key)
        if info is None:
            raise ProblemError(404, ErrorCode.NOT_FOUND)
        start, end = 0, max(info.size - 1, 0)
        if range is not None:
            start = range[0]
            end = info.size - 1 if range[1] is None else min(range[1], info.size - 1)
            if start >= info.size or start > end:
                raise ProblemError(
                    416, ErrorCode.RANGE_NOT_SATISFIABLE, headers={"Content-Range": f"bytes */{info.size}"}
                )

        async def body() -> AsyncIterator[bytes]:
            if info.size == 0:
                return
            async with self.client() as c:
                r = await c.get_object(Bucket=bucket, Key=key, Range=f"bytes={start}-{end}")
                stream = r["Body"]
                try:
                    while chunk := await stream.read(chunk_size):
                        yield chunk
                finally:
                    stream.close()

        return ObjectStream(
            body=body(), size=info.size, start=start, end=end, etag=info.etag, content_type=info.content_type
        )
