from __future__ import annotations

from app.rag.agentic.schemas import EvidenceGrade, KnowledgeSearchResult
from app.rag.agentic.state import RetrievalState


def build_context(state: RetrievalState) -> RetrievalState:
    grade = state.get("evidence_grade") or EvidenceGrade(
        relevant=False,
        sufficient=False,
        coverage_score=0.0,
        relevant_chunk_ids=[],
        missing_information=["未获得可评估证据"],
        conflicts=[],
        next_action="continue_search",
        reason="检索流程未产生证据评分",
    )
    evidence = state.get("accepted_documents", [])
    result = KnowledgeSearchResult(
        answer_context=_answer_context(evidence),
        evidence=evidence,
        sufficient=grade.sufficient,
        evidence_insufficient=not grade.sufficient,
        retrieval_rounds=state.get("retrieval_round", 0),
        queries_used=state.get("previous_queries", []),
        grade=grade,
    )
    return {
        "final_result": result,
        "evidence_insufficient": result.evidence_insufficient,
    }


def _answer_context(evidence: list[object]) -> str:
    if not evidence:
        return "当前知识库未提供可用于回答的可靠证据。"
    return "\n\n".join(
        "\n".join(
            [
                f"chunk_id: {chunk.chunk_id}",
                f"title: {chunk.title}",
                f"source: {chunk.source}",
                f"content: {chunk.content}",
            ]
        )
        for chunk in evidence
    )
