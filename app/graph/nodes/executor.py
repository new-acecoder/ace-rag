from __future__ import annotations

from app.graph.nodes.common import current_plan_step, pending_steps
from app.graph.state import AceRagState, StepResult
from app.streaming.events import emit_event


def select_next_step(state: AceRagState) -> AceRagState:
    pending = pending_steps(state)
    if not pending:
        raise ValueError("no pending plan step is available")
    step = pending[0]
    step_index = next(
        index for index, candidate in enumerate(state.get("plan", [])) if candidate.step_id == step.step_id
    )
    emit_event(
        "step",
        step_id=step.step_id,
        goal=step.goal,
        search_query=step.search_query,
        status="started",
        completed=len(state.get("completed_steps", [])),
        total=len(state.get("completed_steps", [])) + len(pending),
    )
    return {
        "current_step_index": step_index,
        "current_query": step.search_query,
        "retrieval_batch": [],
        "retrieval_grade": None,
    }


def complete_current_step(state: AceRagState) -> AceRagState:
    step = current_plan_step(state)
    grade = state.get("retrieval_grade")
    relevant_ids = set(grade.relevant_chunk_ids) if grade is not None else set()
    evidence = [
        chunk
        for chunk in state.get("retrieved_chunks", [])
        if chunk.chunk_id in relevant_ids
    ]
    completed = state.get("completed_steps", [])
    if any(result.step_id == step.step_id for result in completed):
        raise ValueError("plan step cannot be completed twice")
    result = StepResult(step_id=step.step_id, evidence=list(evidence))
    completed_steps = [*completed, result]
    pending_after = [candidate for candidate in pending_steps({**state, "completed_steps": completed_steps})]
    emit_event(
        "step",
        step_id=step.step_id,
        goal=step.goal,
        search_query=step.search_query,
        status="completed",
        completed=len(completed_steps),
        total=len(completed_steps) + len(pending_after),
    )
    return {
        "completed_steps": completed_steps,
        "intermediate_results": [*state.get("intermediate_results", []), result],
        "retrieval_grade": None,
    }
