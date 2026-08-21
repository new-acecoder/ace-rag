from __future__ import annotations

from typing import TypedDict

from app.rag.agentic.schemas import (
    EvidenceGrade,
    KnowledgeSearchResult,
    RetrievalPlan,
    RetrievalRefinement,
    SearchStrategy,
)
from app.rag.schemas import RetrievedChunk


class RetrievalState(TypedDict, total=False):
    original_query: str
    goal: str
    requested_top_k: int
    max_retrieval_rounds: int
    max_queries_per_round: int
    thinking_enabled: bool

    retrieval_plan: RetrievalPlan | None
    refinement: RetrievalRefinement | None
    current_strategy: SearchStrategy
    current_queries: list[str]
    previous_queries: list[str]

    candidate_documents: list[RetrievedChunk]
    accepted_documents: list[RetrievedChunk]
    evidence_grade: EvidenceGrade | None
    retrieval_round: int
    evidence_insufficient: bool
    force_stop: bool
    final_result: KnowledgeSearchResult | None
