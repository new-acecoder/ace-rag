import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.core.errors import DocumentIngestionError
from app.ingestion.jobs import IngestionJobRecord
from app.ingestion.kernel import IngestionKernel
from app.rag.schemas import IngestionJob


class FakeObjectStore:
    async def read(self, object_key: str) -> bytes:
        assert object_key == "documents/document-1/original.txt"
        return "住宿标准为每晚 500 元。".encode()


class FakeJobs:
    def __init__(self) -> None:
        self.stages: list[str] = []

    async def set_stage(self, _: str, stage: str) -> None:
        self.stages.append(stage)

    async def is_cancel_requested(self, _: str) -> bool:
        return False


class FakeEmbeddingService:
    def __init__(self, vectors: list[list[float]]) -> None:
        self.vectors = vectors

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        assert texts
        return self.vectors


class FakeRepository:
    def __init__(self, deleted: bool = False) -> None:
        self.deleted = deleted
        self.collection_dimensions: list[tuple[int, str]] = []
        self.inserted_chunk_count = 0

    async def ensure_collection(self, dimension: int, collection_name: str) -> None:
        self.collection_dimensions.append((dimension, collection_name))

    async def insert(self, chunks: list[object], vectors: list[list[float]], collection_name: str) -> None:
        assert len(chunks) == len(vectors)
        assert collection_name == "ace_rag_chunks"
        self.inserted_chunk_count = len(chunks)

    async def delete_document(self, _: str, __: str) -> bool:
        return self.deleted


class FakeRetrievalCache:
    def __init__(self) -> None:
        self.increment_calls = 0

    async def increment_index_version(self) -> None:
        self.increment_calls += 1


def record() -> IngestionJobRecord:
    now = datetime(2026, 8, 20, tzinfo=UTC)
    job = IngestionJob(
        job_id="6284e739-1b95-4269-b529-49f61e9ed2e0",
        document_id="e1a15f29-8b69-4f94-881e-0f4043965afe",
        source="travel-policy.txt",
        document_type="txt",
        status="processing",
        stage="parsing",
        chunk_count=None,
        error_code=None,
        error_message=None,
        created_at=now,
        updated_at=now,
    )
    return IngestionJobRecord(
        job=job,
        object_key="documents/document-1/original.txt",
        collection_name="ace_rag_chunks",
        embedding_model_name="BAAI/bge-m3",
        attempt_count=1,
        available_at=now,
    )


def kernel(
    jobs: FakeJobs,
    embeddings: FakeEmbeddingService,
    repository: FakeRepository,
    cache: FakeRetrievalCache,
) -> IngestionKernel:
    return IngestionKernel(
        settings=SimpleNamespace(
            embedding_model_name="BAAI/bge-m3",
            rag_chunk_size_chars=800,
            rag_chunk_overlap_chars=120,
        ),
        object_store=FakeObjectStore(),
        jobs=jobs,
        embedding_service=embeddings,
        repository=repository,
        retrieval_cache=cache,
    )


def test_ingestion_kernel_runs_the_fixed_five_steps() -> None:
    jobs = FakeJobs()
    repository = FakeRepository()
    cache = FakeRetrievalCache()
    service = kernel(jobs, FakeEmbeddingService([[0.1, 0.2]]), repository, cache)

    chunk_count = asyncio.run(service.ingest(record()))

    assert chunk_count == 1
    assert jobs.stages == ["parsing", "splitting", "embedding", "indexing"]
    assert repository.collection_dimensions == [(2, "ace_rag_chunks")]
    assert repository.inserted_chunk_count == 1
    assert cache.increment_calls == 1


def test_ingestion_kernel_rejects_empty_embedding_dimension() -> None:
    jobs = FakeJobs()
    repository = FakeRepository()
    cache = FakeRetrievalCache()
    service = kernel(jobs, FakeEmbeddingService([[]]), repository, cache)

    with pytest.raises(DocumentIngestionError):
        asyncio.run(service.ingest(record()))

    assert repository.collection_dimensions == []
    assert repository.inserted_chunk_count == 0


def test_cleanup_invalidates_retrieval_cache_when_chunks_were_deleted() -> None:
    jobs = FakeJobs()
    repository = FakeRepository(deleted=True)
    cache = FakeRetrievalCache()
    service = kernel(jobs, FakeEmbeddingService([[0.1, 0.2]]), repository, cache)

    asyncio.run(service.cleanup_chunks(record()))

    assert cache.increment_calls == 1
