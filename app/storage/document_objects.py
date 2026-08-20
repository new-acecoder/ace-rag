from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import UploadFile
from minio import Minio
from minio.error import S3Error

from app.core.config import Settings
from app.core.errors import ServiceUnavailableError


class DocumentObjectStore:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def store_upload(self, document_id: str, file: UploadFile) -> str:
        object_key = f"documents/{document_id}/original{Path(file.filename or '').suffix.lower()}"
        try:
            await asyncio.to_thread(self._store_upload, object_key, file)
        except Exception as error:
            raise ServiceUnavailableError("MinIO") from error
        return object_key

    async def read(self, object_key: str) -> bytes:
        try:
            return await asyncio.to_thread(self._read, object_key)
        except Exception as error:
            raise ServiceUnavailableError("MinIO") from error

    async def remove(self, object_key: str) -> None:
        try:
            await asyncio.to_thread(self._client().remove_object, self._settings.minio_upload_bucket, object_key)
        except Exception as error:
            raise ServiceUnavailableError("MinIO") from error

    async def check_health(self) -> None:
        try:
            await asyncio.to_thread(self._ensure_bucket)
        except Exception as error:
            raise ServiceUnavailableError("MinIO") from error

    def _client(self) -> Minio:
        return Minio(
            self._settings.minio_endpoint,
            access_key=self._settings.minio_access_key.get_secret_value(),
            secret_key=self._settings.minio_secret_key.get_secret_value(),
            secure=self._settings.minio_secure,
        )

    def _ensure_bucket(self) -> None:
        client = self._client()
        if client.bucket_exists(self._settings.minio_upload_bucket):
            return
        try:
            client.make_bucket(self._settings.minio_upload_bucket)
        except S3Error as error:
            if error.code not in {"BucketAlreadyExists", "BucketAlreadyOwnedByYou"}:
                raise

    def _store_upload(self, object_key: str, file: UploadFile) -> None:
        self._ensure_bucket()
        file.file.seek(0)
        file_size = file.size
        if file_size is None:
            file.file.seek(0, 2)
            file_size = file.file.tell()
            file.file.seek(0)
        self._client().put_object(
            self._settings.minio_upload_bucket,
            object_key,
            file.file,
            length=file_size,
            content_type=file.content_type or "application/octet-stream",
        )

    def _read(self, object_key: str) -> bytes:
        response = self._client().get_object(self._settings.minio_upload_bucket, object_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()
