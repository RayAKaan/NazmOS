"""Storage abstraction for NazmOS uploads and generated files.

Supports three backends:
  - local: saves files to the local UPLOAD_DIR (default, zero-cost).
  - s3:    AWS S3 via the boto3 SDK (requires STORAGE_BUCKET).
  - minio: S3-compatible storage via the MinIO SDK (requires STORAGE_ENDPOINT and bucket).

Selection is controlled by the STORAGE_BACKEND env var. Missing S3/MinIO credentials
gracefully fall back to local storage with a warning so the backend keeps running in
development without live object-store credentials.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO

import aiofiles

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


def _make_key(filename: str, prefix: str | None = None) -> str:
    """Build a clean, collision-resistant object key."""
    safe_name = Path(filename).name
    unique_name = f"{uuid.uuid4().hex[:8]}_{safe_name}"
    if prefix:
        prefix = prefix.strip("/")
        return f"{prefix}/{unique_name}"
    return unique_name


class StorageBackend(ABC):
    """Abstract storage backend."""

    @abstractmethod
    async def store(self, filename: str, content: bytes, content_type: str | None = None) -> str:
        """Persist a file and return a URI/path that can be used to retrieve it."""

    @abstractmethod
    async def retrieve(self, key: str) -> bytes:
        """Return the contents of the stored object."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Remove the stored object."""

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Return True if the object exists."""


class LocalStorageBackend(StorageBackend):
    """Default zero-cost backend: writes files to the configured UPLOAD_DIR."""

    def __init__(self, base_dir: str | Path | None = None):
        self.base_dir = Path(base_dir or settings.UPLOAD_DIR)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def store(self, filename: str, content: bytes, content_type: str | None = None) -> str:
        key = _make_key(filename)
        path = self.base_dir / key
        async with aiofiles.open(path, "wb") as f:
            await f.write(content)
        return str(path)

    async def retrieve(self, key: str) -> bytes:
        path = self.base_dir / Path(key).name
        async with aiofiles.open(path, "rb") as f:
            return await f.read()

    async def delete(self, key: str) -> None:
        path = self.base_dir / Path(key).name
        if path.exists():
            await asyncio.to_thread(path.unlink)

    async def exists(self, key: str) -> bool:
        path = self.base_dir / Path(key).name
        return path.exists()


class S3StorageBackend(StorageBackend):
    """AWS S3 backend using boto3. Falls back to local storage if boto3 is missing."""

    def __init__(self) -> None:
        try:
            import boto3  # type: ignore
        except ImportError as exc:  # pragma: no cover
            logger.warning("boto3 is not installed; falling back to local storage")
            raise RuntimeError("boto3 not installed") from exc

        self.bucket = settings.STORAGE_BUCKET
        self.prefix = settings.STORAGE_PREFIX
        self.client = boto3.client(
            "s3",
            region_name=settings.STORAGE_REGION,
            endpoint_url=settings.STORAGE_ENDPOINT or None,
            aws_access_key_id=settings.STORAGE_ACCESS_KEY or None,
            aws_secret_access_key=settings.STORAGE_SECRET_KEY or None,
        )

    async def store(self, filename: str, content: bytes, content_type: str | None = None) -> str:
        key = _make_key(filename, self.prefix)
        extra_args = {"ContentType": content_type} if content_type else {}
        await asyncio.to_thread(self.client.put_object, Bucket=self.bucket, Key=key, Body=content, **extra_args)
        return f"s3://{self.bucket}/{key}"

    async def retrieve(self, key: str) -> bytes:
        real_key = key.replace(f"s3://{self.bucket}/", "")
        response = await asyncio.to_thread(self.client.get_object, Bucket=self.bucket, Key=real_key)
        return response["Body"].read()

    async def delete(self, key: str) -> None:
        real_key = key.replace(f"s3://{self.bucket}/", "")
        await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket, Key=real_key)

    async def exists(self, key: str) -> bool:
        real_key = key.replace(f"s3://{self.bucket}/", "")
        try:
            await asyncio.to_thread(self.client.head_object, Bucket=self.bucket, Key=real_key)
            return True
        except Exception:
            return False


class MinIOStorageBackend(StorageBackend):
    """S3-compatible backend using the MinIO SDK (already in requirements.txt)."""

    def __init__(self) -> None:
        from minio import Minio  # type: ignore
        from minio.error import S3Error  # type: ignore

        self._S3Error = S3Error
        endpoint = settings.STORAGE_ENDPOINT
        if not endpoint:
            raise RuntimeError("STORAGE_ENDPOINT is required for minio backend")

        use_ssl = settings.STORAGE_USE_SSL
        self.bucket = settings.STORAGE_BUCKET
        self.prefix = settings.STORAGE_PREFIX
        self.client = Minio(
            endpoint.replace("https://", "").replace("http://", ""),
            access_key=settings.STORAGE_ACCESS_KEY,
            secret_key=settings.STORAGE_SECRET_KEY,
            secure=use_ssl,
        )

    async def store(self, filename: str, content: bytes, content_type: str | None = None) -> str:
        key = _make_key(filename, self.prefix)
        from io import BytesIO

        await asyncio.to_thread(
            self.client.put_object,
            self.bucket,
            key,
            BytesIO(content),
            length=len(content),
            content_type=content_type or "application/octet-stream",
        )
        return f"s3://{self.bucket}/{key}"

    async def retrieve(self, key: str) -> bytes:
        real_key = key.replace(f"s3://{self.bucket}/", "")
        response = await asyncio.to_thread(self.client.get_object, self.bucket, real_key)
        return response.read()

    async def delete(self, key: str) -> None:
        real_key = key.replace(f"s3://{self.bucket}/", "")
        await asyncio.to_thread(self.client.remove_object, self.bucket, real_key)

    async def exists(self, key: str) -> bool:
        real_key = key.replace(f"s3://{self.bucket}/", "")
        try:
            await asyncio.to_thread(self.client.stat_object, self.bucket, real_key)
            return True
        except self._S3Error:
            return False


def get_storage_backend() -> StorageBackend:
    """Return the configured storage backend, falling back to local on misconfiguration."""
    backend = settings.STORAGE_BACKEND.lower()

    if backend == "s3":
        try:
            return S3StorageBackend()
        except Exception as exc:
            logger.warning("S3 storage backend failed to initialize (%s); using local storage", exc)
            return LocalStorageBackend()

    if backend == "minio":
        try:
            return MinIOStorageBackend()
        except Exception as exc:
            logger.warning("MinIO storage backend failed to initialize (%s); using local storage", exc)
            return LocalStorageBackend()

    return LocalStorageBackend()


# Module-level singleton for router/service use.
storage = get_storage_backend()
