from __future__ import annotations

import asyncio

from pymilvus import AnnSearchRequest, DataType, Function, FunctionType, MilvusClient, RRFRanker

from app.core.config import Settings
from app.core.errors import ApiException, DocumentIngestionError, ServiceUnavailableError
from app.rag.schemas import DocumentInfo, DocumentItem, IngestionChunk, RetrievedChunk


_RETRIEVED_CHUNK_FIELDS = [
    "document_id",
    "chunk_id",
    "chunk_index",
    "content",
    "title",
    "page_number",
    "source",
    "document_type",
    "version",
    "updated_at",
]


class MilvusChunkRepository:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def ensure_collection(
        self,
        dense_dimension: int,
        collection_name: str | None = None,
    ) -> None:
        try:
            await asyncio.to_thread(
                self._ensure_collection,
                dense_dimension,
                collection_name or self._settings.milvus_collection_name,
            )
        except ApiException:
            raise
        except Exception as error:
            raise ServiceUnavailableError("Milvus") from error

    async def insert(
        self,
        chunks: list[IngestionChunk],
        vectors: list[list[float]],
        collection_name: str | None = None,
    ) -> None:
        if len(chunks) != len(vectors) or not vectors:
            raise DocumentIngestionError()
        try:
            await asyncio.to_thread(
                self._insert,
                chunks,
                vectors,
                collection_name or self._settings.milvus_collection_name,
            )
        except ApiException:
            raise
        except Exception as error:
            raise ServiceUnavailableError("Milvus") from error

    async def list_documents(self) -> list[DocumentItem]:
        try:
            return await asyncio.to_thread(self._list_documents)
        except Exception as error:
            raise ServiceUnavailableError("Milvus") from error

    async def hybrid_search(
        self,
        query: str,
        query_vector: list[float],
        dense_top_k: int,
        bm25_top_k: int,
        final_top_k: int,
    ) -> list[RetrievedChunk]:
        try:
            return await asyncio.to_thread(
                self._hybrid_search,
                query,
                query_vector,
                dense_top_k,
                bm25_top_k,
                final_top_k,
            )
        except Exception as error:
            raise ServiceUnavailableError("Milvus") from error

    async def get_document_context(
        self,
        document_id: str,
        chunk_id: str,
        window: int,
    ) -> list[RetrievedChunk]:
        try:
            return await asyncio.to_thread(
                self._get_document_context,
                document_id,
                chunk_id,
                window,
            )
        except Exception as error:
            raise ServiceUnavailableError("Milvus") from error

    async def get_document_info(self, document_id: str) -> DocumentInfo | None:
        try:
            return await asyncio.to_thread(self._get_document_info, document_id)
        except Exception as error:
            raise ServiceUnavailableError("Milvus") from error

    async def delete_document(
        self,
        document_id: str,
        collection_name: str | None = None,
    ) -> bool:
        try:
            return await asyncio.to_thread(
                self._delete_document,
                document_id,
                collection_name or self._settings.milvus_collection_name,
            )
        except Exception as error:
            raise ServiceUnavailableError("Milvus") from error

    def _client(self) -> MilvusClient:
        return MilvusClient(uri=self._settings.milvus_uri)

    def _ensure_collection(self, dense_dimension: int, collection_name: str) -> None:
        client = self._client()
        if client.has_collection(collection_name):
            fields = client.describe_collection(collection_name).get("fields", [])
            dense_field = next(
                (field for field in fields if field.get("name") == "dense_vector"),
                None,
            )
            if dense_field is None or int(dense_field.get("params", {}).get("dim", 0)) != dense_dimension:
                raise DocumentIngestionError()
            return

        schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field(field_name="id", datatype=DataType.VARCHAR, is_primary=True, max_length=36)
        schema.add_field(field_name="document_id", datatype=DataType.VARCHAR, max_length=36)
        schema.add_field(field_name="chunk_id", datatype=DataType.VARCHAR, max_length=36)
        schema.add_field(field_name="chunk_index", datatype=DataType.INT64)
        schema.add_field(field_name="chunk_count", datatype=DataType.INT64)
        schema.add_field(field_name="title", datatype=DataType.VARCHAR, max_length=1024)
        schema.add_field(
            field_name="content",
            datatype=DataType.VARCHAR,
            max_length=65535,
            enable_analyzer=True,
        )
        schema.add_field(field_name="source", datatype=DataType.VARCHAR, max_length=1024)
        schema.add_field(field_name="document_type", datatype=DataType.VARCHAR, max_length=8)
        schema.add_field(field_name="version", datatype=DataType.VARCHAR, max_length=64)
        schema.add_field(field_name="page_number", datatype=DataType.INT64, nullable=True)
        schema.add_field(field_name="updated_at", datatype=DataType.VARCHAR, max_length=40)
        schema.add_field(field_name="dense_vector", datatype=DataType.FLOAT_VECTOR, dim=dense_dimension)
        schema.add_field(field_name="sparse_vector", datatype=DataType.SPARSE_FLOAT_VECTOR)
        schema.add_function(
            Function(
                name="content_bm25",
                input_field_names=["content"],
                output_field_names=["sparse_vector"],
                function_type=FunctionType.BM25,
            )
        )

        index_params = client.prepare_index_params()
        index_params.add_index(
            field_name="dense_vector",
            index_type="AUTOINDEX",
            metric_type="COSINE",
        )
        index_params.add_index(
            field_name="sparse_vector",
            index_type="SPARSE_INVERTED_INDEX",
            metric_type="BM25",
        )
        client.create_collection(
            collection_name=collection_name,
            schema=schema,
            index_params=index_params,
        )

    def _insert(
        self,
        chunks: list[IngestionChunk],
        vectors: list[list[float]],
        collection_name: str,
    ) -> None:
        dense_dimension = len(vectors[0])
        if any(len(vector) != dense_dimension for vector in vectors):
            raise DocumentIngestionError()
        records = [
            {
                "id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "chunk_id": chunk.chunk_id,
                "chunk_index": chunk.chunk_index,
                "chunk_count": chunk.chunk_count,
                "title": chunk.title,
                "content": chunk.content,
                "source": chunk.source,
                "document_type": chunk.document_type,
                "version": chunk.version,
                "page_number": chunk.page_number,
                "updated_at": chunk.updated_at.isoformat(),
                "dense_vector": vector,
            }
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        client = self._client()
        client.insert(collection_name, records)
        client.flush(collection_name)

    def _list_documents(self) -> list[DocumentItem]:
        client = self._client()
        if not client.has_collection(self._settings.milvus_collection_name):
            return []

        records = client.query(
            collection_name=self._settings.milvus_collection_name,
            filter="chunk_index == 0",
            output_fields=[
                "document_id",
                "title",
                "source",
                "document_type",
                "chunk_count",
                "updated_at",
            ],
            limit=16_384,
        )
        documents = [DocumentItem.model_validate(record) for record in records]
        return sorted(documents, key=lambda document: document.updated_at, reverse=True)

    def _hybrid_search(
        self,
        query: str,
        query_vector: list[float],
        dense_top_k: int,
        bm25_top_k: int,
        final_top_k: int,
    ) -> list[RetrievedChunk]:
        collection_name = self._settings.milvus_collection_name
        client = self._client()
        if not client.has_collection(collection_name):
            return []

        results = client.hybrid_search(
            collection_name=collection_name,
            reqs=[
                AnnSearchRequest(
                    data=[query_vector],
                    anns_field="dense_vector",
                    param={"metric_type": "COSINE", "params": {}},
                    limit=dense_top_k,
                ),
                AnnSearchRequest(
                    data=[query],
                    anns_field="sparse_vector",
                    param={"metric_type": "BM25", "params": {}},
                    limit=bm25_top_k,
                ),
            ],
            ranker=RRFRanker(),
            limit=final_top_k,
            output_fields=_RETRIEVED_CHUNK_FIELDS,
        )
        return [
            self._to_retrieved_chunk(hit["entity"], score=float(hit["distance"]))
            for hit in (results[0] if results else [])
        ]

    def _get_document_context(
        self,
        document_id: str,
        chunk_id: str,
        window: int,
    ) -> list[RetrievedChunk]:
        collection_name = self._settings.milvus_collection_name
        client = self._client()
        if not client.has_collection(collection_name):
            return []

        target = client.query(
            collection_name=collection_name,
            filter=(
                f'document_id == "{document_id}" and chunk_id == "{chunk_id}"'
            ),
            output_fields=["chunk_index"],
            limit=1,
        )
        if not target:
            return []

        chunk_index = int(target[0]["chunk_index"])
        records = client.query(
            collection_name=collection_name,
            filter=(
                f'document_id == "{document_id}" and '
                f"chunk_index >= {max(0, chunk_index - window)} and "
                f"chunk_index <= {chunk_index + window}"
            ),
            output_fields=_RETRIEVED_CHUNK_FIELDS,
            limit=window * 2 + 1,
        )
        return sorted(
            [self._to_retrieved_chunk(record) for record in records],
            key=lambda chunk: chunk.chunk_index,
        )

    def _get_document_info(self, document_id: str) -> DocumentInfo | None:
        collection_name = self._settings.milvus_collection_name
        client = self._client()
        if not client.has_collection(collection_name):
            return None

        records = client.query(
            collection_name=collection_name,
            filter=f'document_id == "{document_id}" and chunk_index == 0',
            output_fields=[
                "document_id",
                "title",
                "version",
                "source",
                "document_type",
                "updated_at",
            ],
            limit=1,
        )
        return DocumentInfo.model_validate(records[0]) if records else None

    @staticmethod
    def _to_retrieved_chunk(
        record: dict[str, object], score: float | None = None
    ) -> RetrievedChunk:
        return RetrievedChunk.model_validate({**record, "score": score})

    def _delete_document(self, document_id: str, collection_name: str) -> bool:
        client = self._client()
        if not client.has_collection(collection_name):
            return False

        records = client.query(
            collection_name=collection_name,
            filter=f'document_id == "{document_id}"',
            output_fields=["id"],
            limit=1,
        )
        if not records:
            return False

        client.delete(
            collection_name=collection_name,
            filter=f'document_id == "{document_id}"',
        )
        client.flush(collection_name)
        return True
