from __future__ import annotations

from contextlib import suppress
from datetime import UTC, datetime

from app.cache.retrieval_cache import RetrievalCache
from app.core.config import Settings
from app.core.errors import DocumentIngestionError, IngestionCancelledError
from app.ingestion.jobs import IngestionJobRecord, IngestionJobRepository
from app.rag.embedding import EmbeddingService
from app.rag.milvus import MilvusChunkRepository
from app.rag.parser import parse_document
from app.rag.splitter import split_document
from app.storage.document_objects import DocumentObjectStore


class IngestionKernel:
    def __init__(
        self,
        settings: Settings,
        object_store: DocumentObjectStore,
        jobs: IngestionJobRepository,
        embedding_service: EmbeddingService,
        repository: MilvusChunkRepository,
        retrieval_cache: RetrievalCache,
    ) -> None:
        self._settings = settings
        self._object_store = object_store
        self._jobs = jobs
        self._embedding_service = embedding_service
        self._repository = repository
        self._retrieval_cache = retrieval_cache

    async def ingest(self, record: IngestionJobRecord) -> int:
        if record.embedding_model_name != self._settings.embedding_model_name:
            raise DocumentIngestionError()

        await self._jobs.set_stage(record.job.job_id, "parsing")
        content = await self._object_store.read(record.object_key)
        parsed_document = parse_document(record.job.source, content)
        await self._check_cancel(record.job.job_id)

        await self._jobs.set_stage(record.job.job_id, "splitting")
        chunks = split_document(
            document=parsed_document,
            document_id=record.job.document_id,
            updated_at=datetime.now(UTC),
            chunk_size=self._settings.rag_chunk_size_chars,
            chunk_overlap=self._settings.rag_chunk_overlap_chars,
        )
        await self._check_cancel(record.job.job_id)

        await self._jobs.set_stage(record.job.job_id, "embedding")
        vectors = await self._embedding_service.embed_documents([chunk.content for chunk in chunks])
        if len(vectors) != len(chunks):
            raise DocumentIngestionError()
        dense_dimension = len(vectors[0])
        if dense_dimension == 0 or any(len(vector) != dense_dimension for vector in vectors):
            raise DocumentIngestionError()
        await self._check_cancel(record.job.job_id)

        await self._jobs.set_stage(record.job.job_id, "indexing")
        await self._repository.ensure_collection(dense_dimension, record.collection_name)
        await self._repository.insert(chunks, vectors, record.collection_name)
        await self._check_cancel(record.job.job_id)
        await self._retrieval_cache.increment_index_version()
        return len(chunks)

    async def cleanup_chunks(self, record: IngestionJobRecord) -> None:
        with suppress(Exception):
            if await self._repository.delete_document(
                record.job.document_id,
                record.collection_name,
            ):
                await self._retrieval_cache.increment_index_version()

    async def cancel(self, record: IngestionJobRecord) -> None:
        await self.cleanup_chunks(record)
        with suppress(Exception):
            await self._object_store.remove(record.object_key)

    async def _check_cancel(self, job_id: str) -> None:
        if await self._jobs.is_cancel_requested(job_id):
            raise IngestionCancelledError()
