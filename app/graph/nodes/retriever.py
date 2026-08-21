from __future__ import annotations

from app.graph.nodes.common import current_plan_step, merge_chunks
from app.graph.services import WorkflowServices
from app.graph.state import AceRagState
from app.rag.agentic.schemas import EvidenceGrade


async def retrieve_chunks(state: AceRagState, services: WorkflowServices) -> AceRagState:
    query = state.get("current_query", "").strip()
    if not query:
        raise ValueError("current_query is required")
    remaining_rounds = services.settings.max_retrieval_count - state.get(
        "retrieval_count", 0
    )
    if remaining_rounds <= 0:
        return {
            "retrieval_batch": [],
            "retrieval_grade": EvidenceGrade(
                relevant=False,
                sufficient=False,
                coverage_score=0.0,
                relevant_chunk_ids=[],
                missing_information=["已达到本轮全局检索次数上限"],
                conflicts=[],
                next_action="continue_search",
                reason="全局检索预算已耗尽",
            ),
            "evidence_insufficient": True,
        }
    goal = (
        current_plan_step(state).goal
        if state.get("route_type") == "plan_execute"
        else state.get("user_query", query)
    )
    result = await services.agentic_retrieval.search(
        query,
        goal=goal,
        thinking_enabled=services.thinking_enabled(state),
        max_rounds=remaining_rounds,
    )
    return {
        "retrieval_batch": result.evidence,
        "retrieved_chunks": merge_chunks(
            state.get("retrieved_chunks", []),
            result.evidence,
        ),
        "retrieval_grade": result.grade,
        "evidence_insufficient": result.evidence_insufficient,
        "queries_used": list(
            dict.fromkeys([*state.get("queries_used", []), *result.queries_used])
        ),
        "retrieval_count": state.get("retrieval_count", 0)
        + result.retrieval_rounds,
    }
