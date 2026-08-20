import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

import pytest

from app.core.errors import DocumentNotFoundError
from app.ingestion.services import DocumentCatalogService
from app.rag.schemas import DocumentItem


class FakeRepository:
    def __init__(self, deleted: bool) -> None:
        self.deleted = deleted
        self.deleted_document_id: str | None = None

    async def list_documents(self) -> list[DocumentItem]:
        return [
            DocumentItem(
                document_id="document-1",
                title="travel-policy",
                source="travel-policy.txt",
                document_type="txt",
                chunk_count=1,
                updated_at=datetime(2026, 8, 20, tzinfo=UTC),
            )
        ]

    async def delete_document(self, document_id: str, collection_name: str | None = None) -> bool:
        self.deleted_document_id = document_id
        return self.deleted


class FakeObjectStore:
    def __init__(self) -> None:
        self.removed: list[str] = []

    async def remove(self, object_key: str) -> None:
        self.removed.append(object_key)


class FakeJobs:
    def __init__(self, has_job: bool) -> None:
        self.has_job = has_job
        self.deleted: list[str] = []

    async def find_by_document_id(self, document_id: str) -> SimpleNamespace | None:
        if not self.has_job:
            return None
        return SimpleNamespace(
            object_key=f"documents/{document_id}/original.txt",
            collection_name="ace_rag_chunks",
        )

    async def delete_by_document_id(self, document_id: str) -> None:
        self.deleted.append(document_id)


class FakeRetrievalCache:
    def __init__(self) -> None:
        self.increment_calls = 0

    async def increment_index_version(self) -> None:
        self.increment_calls += 1


def create_service(
    repository: FakeRepository,
    object_store: FakeObjectStore,
    jobs: FakeJobs,
    cache: FakeRetrievalCache,
) -> DocumentCatalogService:
    return DocumentCatalogService(
        repository=cast(object, repository),
        object_store=cast(object, object_store),
        jobs=cast(object, jobs),
        retrieval_cache=cast(object, cache),
    )


def test_delete_document_removes_source_job_and_invalidates_cache() -> None:
    repository = FakeRepository(deleted=True)
    object_store = FakeObjectStore()
    jobs = FakeJobs(has_job=True)
    cache = FakeRetrievalCache()
    service = create_service(repository, object_store, jobs, cache)

    asyncio.run(service.delete("document-1"))

    assert repository.deleted_document_id == "document-1"
    assert object_store.removed == ["documents/document-1/original.txt"]
    assert jobs.deleted == ["document-1"]
    assert cache.increment_calls == 1


def test_delete_legacy_document_invalidates_cache_without_source_metadata() -> None:
    repository = FakeRepository(deleted=True)
    object_store = FakeObjectStore()
    jobs = FakeJobs(has_job=False)
    cache = FakeRetrievalCache()
    service = create_service(repository, object_store, jobs, cache)

    asyncio.run(service.delete("document-1"))

    assert object_store.removed == []
    assert jobs.deleted == []
    assert cache.increment_calls == 1


def test_delete_missing_document_does_not_invalidate_cache() -> None:
    repository = FakeRepository(deleted=False)
    object_store = FakeObjectStore()
    jobs = FakeJobs(has_job=False)
    cache = FakeRetrievalCache()
    service = create_service(repository, object_store, jobs, cache)

    with pytest.raises(DocumentNotFoundError):
        asyncio.run(service.delete("missing-document"))

    assert cache.increment_calls == 0
