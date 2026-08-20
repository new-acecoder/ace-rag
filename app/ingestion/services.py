from __future__ import annotations

from contextlib import suppress
from uuid import uuid4

from fastapi import UploadFile

from app.cache.retrieval_cache import RetrievalCache
from app.core.config import Settings
from app.core.errors import DocumentNotFoundError, DocumentTooLargeError
from app.ingestion.jobs import IngestionJobRepository
from app.rag.milvus import MilvusChunkRepository
from app.rag.parser import get_document_type
from app.rag.schemas import DocumentItem, IngestionJob
from app.storage.document_objects import DocumentObjectStore


class DocumentUploadService:
    def __init__(
        self,
        settings: Settings,
        object_store: DocumentObjectStore,
        jobs: IngestionJobRepository,
    ) -> None:
        self._settings = settings
        self._object_store = object_store
        self._jobs = jobs

    async def enqueue(self, file: UploadFile) -> IngestionJob:
        document_type = get_document_type(file.filename)
        if self._file_size(file) > self._settings.document_max_upload_bytes:
            raise DocumentTooLargeError()

        document_id = str(uuid4())
        object_key = await self._object_store.store_upload(document_id, file)
        try:
            return await self._jobs.create(
                document_id=document_id,
                source=file.filename or "",
                document_type=document_type,
                object_key=object_key,
            )
        except Exception:
            with suppress(Exception):
                await self._object_store.remove(object_key)
            raise

    @staticmethod
    def _file_size(file: UploadFile) -> int:
        if file.size is not None:
            return file.size
        file.file.seek(0, 2)
        size = file.file.tell()
        file.file.seek(0)
        return size


class DocumentCatalogService:
    def __init__(
        self,
        repository: MilvusChunkRepository,
        object_store: DocumentObjectStore,
        jobs: IngestionJobRepository,
        retrieval_cache: RetrievalCache,
    ) -> None:
        self._repository = repository
        self._object_store = object_store
        self._jobs = jobs
        self._retrieval_cache = retrieval_cache

    async def list_documents(self) -> list[DocumentItem]:
        return await self._repository.list_documents()

    async def delete(self, document_id: str) -> None:
        job = await self._jobs.find_by_document_id(document_id)
        deleted = await self._repository.delete_document(
            document_id,
            job.collection_name if job is not None else None,
        )
        if not deleted:
            raise DocumentNotFoundError()
        if job is not None:
            await self._object_store.remove(job.object_key)
            await self._jobs.delete_by_document_id(document_id)
        await self._retrieval_cache.increment_index_version()
