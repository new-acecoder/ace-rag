from __future__ import annotations

from app.graph.state import AceRagState


def initialize_turn(state: AceRagState) -> AceRagState:
    turn_id = state.get("turn_id")
    user_query = state.get("user_query")
    thinking_enabled = state.get("thinking_enabled")
    if not turn_id:
        raise ValueError("turn_id is required")
    if not user_query:
        raise ValueError("user_query is required")
    if not isinstance(thinking_enabled, bool):
        raise ValueError("thinking_enabled is required")

    return {
        "turn_id": turn_id,
        "user_query": user_query,
        "thinking_enabled": thinking_enabled,
        "route_type": None,
        "required_capabilities": [],
        "current_query": user_query,
        "rewritten_query": None,
        "plan": [],
        "current_step_index": 0,
        "completed_steps": [],
        "intermediate_results": [],
        "retrieval_batch": [],
        "retrieved_chunks": [],
        "retrieval_grade": None,
        "evidence_insufficient": False,
        "queries_used": [],
        "draft_answer": None,
        "cited_chunk_ids": [],
        "sources": [],
        "generation_mode": "normal",
        "answer_status": None,
        "answer_evaluation": None,
        "reflection_decision": None,
        "rewrite_count": 0,
        "replan_count": 0,
        "reflection_count": 0,
        "retrieval_count": 0,
        "error": None,
    }
