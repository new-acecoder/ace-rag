from __future__ import annotations

from typing import TypeVar

from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from app.core.config import Settings
from app.memory.context_manager import ContextManager
from app.models.llm import ChatModelService
from app.rag.agentic.graph import build_retrieval_graph
from app.rag.agentic.schemas import KnowledgeSearchResult
from app.rag.retrieval import RetrievalService
from app.streaming.events import forward_stream_events

StructuredResponse = TypeVar("StructuredResponse", bound=BaseModel)


class AgenticRetrievalRunner:
    def __init__(
        self,
        settings: Settings,
        chat_model: ChatModelService,
        context_manager: ContextManager,
        retrieval_service: RetrievalService,
    ) -> None:
        self._settings = settings
        self._chat_model = chat_model
        self._context_manager = context_manager
        self._retrieval_service = retrieval_service
        self._graph = build_retrieval_graph(retrieval_service, self._structured)

    @property
    def final_top_k(self) -> int:
        return self._retrieval_service.final_top_k

    async def search(
        self,
        question: str,
        *,
        goal: str | None = None,
        top_k: int | None = None,
        thinking_enabled: bool = False,
        max_rounds: int | None = None,
    ) -> KnowledgeSearchResult:
        normalized = question.strip()
        if not normalized:
            raise ValueError("question cannot be blank")
        requested_top_k = top_k or self.final_top_k
        if not 0 < requested_top_k <= self.final_top_k:
            raise ValueError(f"top_k must be between 1 and {self.final_top_k}")
        retrieval_rounds = min(
            max_rounds or self._settings.max_agentic_retrieval_rounds,
            self._settings.max_agentic_retrieval_rounds,
        )
        if retrieval_rounds <= 0:
            raise ValueError("max_rounds must be positive")

        graph_input = {
            "original_query": normalized,
            "goal": (goal or normalized).strip(),
            "requested_top_k": requested_top_k,
            "max_retrieval_rounds": retrieval_rounds,
            "max_queries_per_round": self._settings.max_retrieval_queries_per_round,
            "thinking_enabled": thinking_enabled,
            "retrieval_plan": None,
            "refinement": None,
            "current_queries": [],
            "previous_queries": [],
            "candidate_documents": [],
            "accepted_documents": [],
            "evidence_grade": None,
            "retrieval_round": 0,
            "evidence_insufficient": False,
            "force_stop": False,
            "final_result": None,
        }
        config = {
            "recursion_limit": 4 * retrieval_rounds + 6,
            "tags": ["agentic-retrieval"],
        }
        with forward_stream_events():
            state = await self._graph.ainvoke(graph_input, config=config)
        result = state.get("final_result")
        if not isinstance(result, KnowledgeSearchResult):
            raise RuntimeError("agentic retrieval completed without a result")
        return result

    async def _structured(
        self,
        schema: type[StructuredResponse],
        instruction: str,
        thinking_enabled: bool,
    ) -> StructuredResponse:
        context = await self._context_manager.build_context(
            [HumanMessage(content=instruction)],
            None,
            thinking_enabled,
        )
        return await self._chat_model.structured(
            schema,
            context.messages,
            thinking_enabled,
        )
