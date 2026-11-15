"""Dataset storage: ``app.core.storage.S3`` plus the operations the datasets API needs.

* :meth:`DatasetStorage.put_part_file` streams an upload part from a (spooled) file instead of
  holding up to 64 MiB in memory (core's ``put_part`` takes ``bytes``).
* :meth:`DatasetStorage.head` raises :class:`ObjectNotFoundError` instead of returning ``None``.
* :meth:`DatasetStorage.get_bytes` reads small JSON objects (reports, previews, manifests).
* :meth:`DatasetStorage.iter_object` yields an object or one inclusive byte range (the caller has
  already validated the range against :meth:`head`).

One instance per app (``app.state.datasets_storage``), built by :func:`app.datasets.router.setup_app`
from the core settings. Never issues presigned URLs (ADR-0010).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import IO

from botocore.exceptions import ClientError
from fastapi import Request

from app.core.settings import Settings
from app.core.storage import S3, ObjectInfo

ObjectMeta = ObjectInfo


class ObjectNotFoundError(Exception):
    pass


class DatasetStorage(S3):
    @classmethod
    def from_settings(cls, s: Settings) -> DatasetStorage:
        return cls(s.s3_endpoint_url, s.s3_access_key, s.s3_secret_key, s.s3_region)

    async def put_part_file(
        self, bucket: str, key: str, upload_id: str, part_number: int, body: IO[bytes], length: int
    ) -> str:
        """Upload one part from a file object; returns the unquoted ETag (as core's ``put_part``)."""
        async with self.client() as c:
            r = await c.upload_part(
                Bucket=bucket,
                Key=key,
                UploadId=upload_id,
                PartNumber=part_number,
                Body=body,
                ContentLength=length,
            )
            return r["ETag"].strip('"')

    async def head(self, bucket: str, key: str) -> ObjectInfo:
        info = await self.head_object(bucket, key)
        if info is None:
            raise ObjectNotFoundError(key)
        return info

    async def get_bytes(self, bucket: str, key: str, max_bytes: int = 64 * 1024 * 1024) -> bytes:
        async with self.client() as c:
            try:
                r = await c.get_object(Bucket=bucket, Key=key)
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                    raise ObjectNotFoundError(key) from exc
                raise
            body = r["Body"]
            try:
                if int(r["ContentLength"]) > max_bytes:
                    raise ValueError("object too large")
                data: bytes = await body.read()
            finally:
                body.close()
            return data

    async def iter_object(
        self, bucket: str, key: str, range_: tuple[int, int] | None = None, chunk: int = 1024 * 1024
    ) -> AsyncIterator[bytes]:
        """Yield the object (or the inclusive byte range ``(start, end)``)."""
        async with self.client() as c:
            if range_ is None:
                r = await c.get_object(Bucket=bucket, Key=key)
            else:
                r = await c.get_object(Bucket=bucket, Key=key, Range=f"bytes={range_[0]}-{range_[1]}")
            body = r["Body"]
            try:
                while data := await body.read(chunk):
                    yield data
            finally:
                body.close()


def get_storage(request: Request) -> DatasetStorage:
    storage: DatasetStorage = request.app.state.datasets_storage
    return storage
