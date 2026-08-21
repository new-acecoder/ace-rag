from __future__ import annotations

from langchain_core.tools import BaseTool, tool

from app.rag.agentic.runner import AgenticRetrievalRunner
from app.rag.agentic.schemas import KnowledgeSearchResult
from app.rag.retrieval import RetrievalService
from app.rag.schemas import DocumentInfo, RetrievedChunk
from app.tools.registry import ToolRegistry
from app.tools.types import ToolDefinition


def build_knowledge_tools(
    retrieval_service: RetrievalService,
    agentic_retrieval: AgenticRetrievalRunner,
    thinking_enabled: bool,
) -> list[BaseTool]:
    default_top_k = retrieval_service.final_top_k

    @tool(response_format="content_and_artifact")
    async def search_knowledge_base(
        query: str, top_k: int = default_top_k
    ) -> tuple[str, KnowledgeSearchResult]:
        """使用受控的 Agentic Retrieval 流程搜索内部知识库。

        Use this before answering questions that require knowledge-base evidence.

        Args:
            query: A concise search query focused on the needed evidence.
            top_k: Number of chunks to return, from 1 to the configured final limit.
        """
        result = await agentic_retrieval.search(
            query,
            goal=query,
            top_k=top_k,
            thinking_enabled=thinking_enabled,
        )
        return result.answer_context, result

    @tool(response_format="content_and_artifact")
    async def get_document_context(
        document_id: str, chunk_id: str, window: int = 2
    ) -> tuple[str, list[RetrievedChunk]]:
        """读取命中文档分片及相邻分片的上下文。

        Use this only after a knowledge search returns a chunk whose surrounding
        context is needed to answer accurately.

        Args:
            document_id: UUID of the document returned by knowledge search.
            chunk_id: UUID of the matched chunk returned by knowledge search.
            window: Number of neighboring chunks on each side, from 0 to 2.
        """
        chunks = await retrieval_service.get_document_context(
            document_id,
            chunk_id,
            window,
        )
        return _format_chunks(chunks), chunks

    @tool(response_format="content_and_artifact")
    async def get_document_info(document_id: str) -> tuple[str, DocumentInfo | None]:
        """读取文档的来源、标题、版本和更新时间等辅助信息。

        Use this only for metadata of a document already supported by retrieved
        chunks. This tool does not provide citable evidence by itself.

        Args:
            document_id: UUID of the document returned by knowledge search.
        """
        document = await retrieval_service.get_document_info(document_id)
        if document is None:
            return "未找到该文档。", None
        return (
            "\n".join(
                [
                    f"document_id: {document.document_id}",
                    f"title: {document.title}",
                    f"version: {document.version or '未标注'}",
                    f"source: {document.source}",
                    f"document_type: {document.document_type}",
                    f"updated_at: {document.updated_at.isoformat()}",
                ]
            ),
            document,
        )

    return [search_knowledge_base, get_document_context, get_document_info]


def build_knowledge_registry(
    retrieval_service: RetrievalService,
    agentic_retrieval: AgenticRetrievalRunner,
    thinking_enabled: bool,
) -> ToolRegistry:
    tools = build_knowledge_tools(
        retrieval_service,
        agentic_retrieval,
        thinking_enabled,
    )
    definitions = [
        ToolDefinition(
            tool=tools[0],
            capability="knowledge",
            operation="read",
            safe_argument_names=frozenset({"query", "top_k"}),
            artifact_types=(KnowledgeSearchResult,),
        ),
        ToolDefinition(
            tool=tools[1],
            capability="knowledge",
            operation="read",
            safe_argument_names=frozenset({"document_id", "chunk_id", "window"}),
            artifact_types=(RetrievedChunk,),
        ),
        ToolDefinition(
            tool=tools[2],
            capability="knowledge",
            operation="read",
            safe_argument_names=frozenset({"document_id"}),
            artifact_types=(DocumentInfo,),
        ),
    ]
    return ToolRegistry(definitions)


def _format_chunks(chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return "未找到相关知识库内容。"
    return "\n\n".join(
        [
            "\n".join(
                [
                    f"chunk_id: {chunk.chunk_id}",
                    f"source: {chunk.source}",
                    f"title: {chunk.title}",
                    "content:",
                    chunk.content,
                ]
            )
            for chunk in chunks
        ]
    )
