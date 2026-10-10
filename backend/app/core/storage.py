"""File storage behind one interface: a local folder (development, single) or S3 (scalable).

Callers save and read by *key* ("knowledge/3f2a-sop.pdf"); the key is what the database keeps.
Rows written before keys existed hold a full local path; the local store still reads those.
S3 calls go through the "storage" circuit breaker like every other external service.
"""

import asyncio
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.core.resilience import breaker


class Storage(Protocol):
    name: str

    async def save(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str: ...
    async def read(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...
    async def probe(self) -> str: ...


class LocalStorage:
    name = "local"

    def __init__(self, root: str) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        legacy = Path(key)
        if legacy.exists() and (legacy.is_absolute() or legacy.parts[:1] == self.root.parts[:1]):
            return legacy  # saved before keys: the full path is stored
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise NotFoundError("We could not find that file.")  # no ../ escapes
        return path

    async def save(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)
        return key

    async def read(self, key: str) -> bytes:
        path = self._path(key)
        if not path.exists():
            raise NotFoundError("We could not find that file.")
        return await asyncio.to_thread(path.read_bytes)

    async def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    async def probe(self) -> str:
        self.root.mkdir(parents=True, exist_ok=True)
        probe = self.root / ".write-probe"
        probe.write_text("ok")
        probe.unlink()
        return "up"


class S3Storage:
    name = "s3"

    def __init__(self, bucket: str, prefix: str, region: str, endpoint_url: str | None) -> None:
        import aioboto3

        self.bucket = bucket
        self.prefix = prefix.strip("/") + "/" if prefix.strip("/") else ""
        self.session = aioboto3.Session()
        self.client_args: dict[str, Any] = {"region_name": region, "endpoint_url": endpoint_url}

    def _key(self, key: str) -> str:
        return f"{self.prefix}{key.lstrip('/')}"

    async def _call(self, method: str, **kwargs: Any) -> Any:
        async def run() -> Any:
            async with self.session.client("s3", **self.client_args) as s3:
                return await getattr(s3, method)(Bucket=self.bucket, **kwargs)

        return await breaker("storage", failure_threshold=3).call(run, timeout=30)

    async def save(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        await self._call("put_object", Key=self._key(key), Body=data, ContentType=content_type, ServerSideEncryption="AES256")
        return key

    async def read(self, key: str) -> bytes:
        async def run() -> bytes:
            async with self.session.client("s3", **self.client_args) as s3:
                try:
                    obj = await s3.get_object(Bucket=self.bucket, Key=self._key(key))
                except s3.exceptions.NoSuchKey as exc:
                    raise NotFoundError("We could not find that file.") from exc
                async with obj["Body"] as body:
                    return await body.read()

        return await breaker("storage", failure_threshold=3).call(run, timeout=30)

    async def delete(self, key: str) -> None:
        await self._call("delete_object", Key=self._key(key))

    async def probe(self) -> str:
        await self._call("head_bucket")
        return "up"


_override: Storage | None = None


@lru_cache
def _configured() -> Storage:
    settings = get_settings()
    if settings.storage_backend == "s3" and settings.s3_bucket:
        return S3Storage(settings.s3_bucket, settings.s3_prefix, settings.aws_region, settings.s3_endpoint_url)
    return LocalStorage(settings.upload_dir)


def get_storage() -> Storage:
    return _override or _configured()


def set_storage(storage: Storage | None) -> None:
    """Tests swap in a store."""
    global _override
    _override = storage
