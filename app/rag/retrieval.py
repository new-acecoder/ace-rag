from __future__ import annotations

from uuid import UUID

from app.cache.retrieval_cache import RetrievalCache
from app.core.config import Settings
from app.rag.embedding import EmbeddingService
from app.rag.milvus import MilvusChunkRepository
from app.rag.schemas import DocumentInfo, RetrievedChunk


class RetrievalService:
    """The only retrieval path shared by graph nodes and knowledge tools."""

    def __init__(
        self,
        settings: Settings,
        embedding_service: EmbeddingService,
        repository: MilvusChunkRepository,
        retrieval_cache: RetrievalCache,
    ) -> None:
        self._settings = settings
        self._embedding_service = embedding_service
        self._repository = repository
        self._retrieval_cache = retrieval_cache

    @property
    def final_top_k(self) -> int:
        return self._settings.rag_final_top_k

    async def search(self, query: str, top_k: int | None = None) -> list[RetrievedChunk]:
        normalized_query = query.strip()
        if not normalized_query:
            return []

        result_top_k = top_k or self.final_top_k
        if not 0 < result_top_k <= self.final_top_k:
            raise ValueError(f"top_k must be between 1 and {self.final_top_k}")

        cached = await self._retrieval_cache.get(normalized_query, result_top_k)
        if cached is not None:
            return cached

        query_vector = await self._embedding_service.embed_query(normalized_query)
        chunks = await self._repository.hybrid_search(
            query=normalized_query,
            query_vector=query_vector,
            dense_top_k=self._settings.rag_dense_top_k,
            bm25_top_k=self._settings.rag_bm25_top_k,
            final_top_k=result_top_k,
        )
        await self._retrieval_cache.set(normalized_query, result_top_k, chunks)
        return chunks

    async def get_document_context(
        self,
        document_id: str,
        chunk_id: str,
        window: int = 2,
    ) -> list[RetrievedChunk]:
        if not 0 <= window <= 2:
            raise ValueError("window must be between 0 and 2")
        return await self._repository.get_document_context(
            document_id=self._uuid(document_id, "document_id"),
            chunk_id=self._uuid(chunk_id, "chunk_id"),
            window=window,
        )

    async def get_document_info(self, document_id: str) -> DocumentInfo | None:
        return await self._repository.get_document_info(
            self._uuid(document_id, "document_id")
        )

    @staticmethod
    def _uuid(value: str, field_name: str) -> str:
        try:
            return str(UUID(value))
        except (AttributeError, TypeError, ValueError) as error:
            raise ValueError(f"{field_name} must be a UUID") from error
