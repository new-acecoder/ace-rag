from __future__ import annotations

from app.graph.nodes.common import insufficient_evidence_answer
from app.graph.state import AceRagState


def enter_best_effort(state: AceRagState) -> AceRagState:
    if state.get("retrieved_chunks"):
        return {"generation_mode": "best_effort", "answer_status": None}
    return {
        "generation_mode": "best_effort",
        "draft_answer": insufficient_evidence_answer(),
        "cited_chunk_ids": [],
        "answer_status": "best_effort",
    }


def finalize_insufficient_evidence(state: AceRagState) -> AceRagState:
    return {
        "generation_mode": "best_effort",
        "draft_answer": insufficient_evidence_answer(),
        "cited_chunk_ids": [],
        "answer_status": "best_effort",
    }
