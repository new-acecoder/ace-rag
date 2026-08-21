from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.rag.schemas import RetrievedChunk

RetrievalStrategy = Literal["single", "rewrite", "multi_query", "decompose"]
RefinementAction = Literal["rewrite", "multi_query", "decompose", "next_hop"]
SearchStrategy = Literal["single", "rewrite", "multi_query", "decompose", "next_hop"]
EvidenceAction = Literal[
    "answer",
    "rewrite",
    "multi_query",
    "decompose",
    "continue_search",
]


class RetrievalPlan(BaseModel):
    strategy: RetrievalStrategy
    queries: list[str]
    top_k: int = Field(default=5, ge=1)
    reason: str


class EvidenceGrade(BaseModel):
    relevant: bool
    sufficient: bool
    coverage_score: float = Field(ge=0.0, le=1.0)
    relevant_chunk_ids: list[str]
    missing_information: list[str]
    conflicts: list[str]
    next_action: EvidenceAction
    reason: str

    @property
    def missing_aspects(self) -> list[str]:
        """Compatibility view for existing parent workflow prompts."""

        return self.missing_information


class RetrievalRefinement(BaseModel):
    action: RefinementAction
    queries: list[str]
    reason: str


class KnowledgeSearchResult(BaseModel):
    answer_context: str
    evidence: list[RetrievedChunk]
    sufficient: bool
    evidence_insufficient: bool
    retrieval_rounds: int = Field(ge=0)
    queries_used: list[str]
    grade: EvidenceGrade
