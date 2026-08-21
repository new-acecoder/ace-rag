from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.graph.nodes.answer_evaluator import evaluate_answer
from app.graph.nodes.best_effort import enter_best_effort, finalize_insufficient_evidence
from app.graph.nodes.common import citations_match_answer
from app.graph.nodes.executor import complete_current_step, select_next_step
from app.graph.nodes.finalize_answer import finalize_answer
from app.graph.nodes.general_chat import answer_general_chat
from app.graph.nodes.generator import generate_answer
from app.graph.nodes.initialize_turn import initialize_turn
from app.graph.nodes.planner import plan_question
from app.graph.nodes.react_adapter import run_react_agent
from app.graph.nodes.reflection import reflect_on_answer
from app.graph.nodes.replanner import replan
from app.graph.nodes.retriever import retrieve_chunks
from app.graph.nodes.router import route_question
from app.graph.services import WorkflowServices
from app.graph.state import AceRagState
from app.streaming.events import emit_event

NodeHandler = Callable[[AceRagState], AceRagState | Awaitable[AceRagState]]


def build_parent_graph(checkpointer: BaseCheckpointSaver, services: WorkflowServices):
    builder = StateGraph(AceRagState)
    builder.add_node("initialize_turn", _tracked("initialize_turn", initialize_turn))
    builder.add_node("router", _tracked("router", lambda state: route_question(state, services)))
    builder.add_node(
        "general_chat",
        _tracked("general_chat", lambda state: answer_general_chat(state, services)),
    )
    builder.add_node(
        "react_adapter",
        _tracked("react_adapter", lambda state: run_react_agent(state, services)),
    )
    builder.add_node("planner", _tracked("planner", lambda state: plan_question(state, services)))
    builder.add_node("executor_select", _tracked("executor", select_next_step))
    builder.add_node(
        "retriever",
        _tracked("retriever", lambda state: retrieve_chunks(state, services)),
    )
    builder.add_node("executor_complete", _tracked("executor", complete_current_step))
    builder.add_node("replanner", _tracked("replanner", lambda state: replan(state, services)))
    builder.add_node(
        "generator",
        _tracked("generator", lambda state: generate_answer(state, services)),
    )
    builder.add_node(
        "answer_evaluator",
        _tracked("answer_evaluator", lambda state: evaluate_answer(state, services)),
    )
    builder.add_node(
        "reflection",
        _tracked("reflection", lambda state: reflect_on_answer(state, services)),
    )
    builder.add_node("best_effort", _tracked("generator", enter_best_effort))
    builder.add_node("fallback_answer", _tracked("generator", finalize_insufficient_evidence))
    builder.add_node("finalize_answer", _tracked("finalize_answer", finalize_answer))

    builder.add_edge(START, "initialize_turn")
    builder.add_edge("initialize_turn", "router")
    builder.add_conditional_edges("router", _route_after_router)
    builder.add_edge("general_chat", "finalize_answer")
    builder.add_conditional_edges(
        "react_adapter",
        _route_after_retrieval,
    )
    builder.add_edge("planner", "executor_select")
    builder.add_edge("executor_select", "retriever")
    builder.add_conditional_edges(
        "retriever",
        _route_after_retrieval,
    )
    builder.add_edge("executor_complete", "replanner")
    builder.add_conditional_edges("replanner", _route_after_replan)
    builder.add_edge("generator", "answer_evaluator")
    builder.add_conditional_edges(
        "answer_evaluator",
        lambda state: _route_after_answer_evaluation(state, services),
    )
    builder.add_conditional_edges("reflection", _route_after_reflection)
    builder.add_conditional_edges("best_effort", _route_after_best_effort)
    builder.add_edge("fallback_answer", "finalize_answer")
    builder.add_edge("finalize_answer", END)
    return builder.compile(checkpointer=checkpointer)


def _route_after_router(
    state: AceRagState,
) -> Literal["general_chat", "react_adapter", "planner"]:
    route_type = state.get("route_type")
    if route_type == "general_chat":
        return "general_chat"
    return "react_adapter" if route_type == "react" else "planner"


def _route_after_retrieval(
    state: AceRagState,
) -> Literal[
    "answer_evaluator",
    "executor_complete",
    "generator",
    "best_effort",
    "finalize_answer",
]:
    if state.get("answer_status") is not None:
        return "finalize_answer"
    grade = state.get("retrieval_grade")
    if grade is not None and grade.sufficient:
        if state.get("route_type") != "react":
            return "executor_complete"
        return "answer_evaluator" if _react_draft_is_grounded(state) else "generator"
    return "best_effort"


def _react_draft_is_grounded(state: AceRagState) -> bool:
    answer = state.get("draft_answer")
    cited_chunk_ids = state.get("cited_chunk_ids", [])
    relevant_chunk_ids = {
        chunk.chunk_id for chunk in state.get("retrieved_chunks", [])
    }
    return (
        bool(answer)
        and citations_match_answer(answer, cited_chunk_ids)
        and set(cited_chunk_ids).issubset(relevant_chunk_ids)
    )


def _route_after_replan(
    state: AceRagState,
) -> Literal["executor_select", "generator"]:
    completed_ids = {result.step_id for result in state.get("completed_steps", [])}
    pending = [step for step in state.get("plan", []) if step.step_id not in completed_ids]
    return "generator" if not pending else "executor_select"


def _route_after_answer_evaluation(
    state: AceRagState,
    services: WorkflowServices,
) -> Literal["finalize_answer", "reflection", "best_effort", "fallback_answer"]:
    if state.get("answer_status") is not None:
        return "finalize_answer"
    if state.get("generation_mode") == "best_effort":
        return "fallback_answer"
    if (
        state.get("retrieval_count", 0) >= services.settings.max_retrieval_count
        or state.get("replan_count", 0) >= services.settings.max_replan_count
        or state.get("reflection_count", 0) >= services.settings.max_reflection_count
    ):
        return "best_effort"
    return "reflection"


def _route_after_reflection(
    state: AceRagState,
) -> Literal["generator", "retriever", "replanner"]:
    decision = state.get("reflection_decision")
    if decision is None:
        raise ValueError("reflection_decision is required")
    if decision.next_action == "regenerate":
        return "generator"
    if state.get("route_type") == "plan_execute":
        return "replanner"
    return "retriever"


def _route_after_best_effort(state: AceRagState) -> Literal["generator", "finalize_answer"]:
    return "generator" if state.get("retrieved_chunks") else "finalize_answer"


def _tracked(name: str, handler: NodeHandler) -> Callable[[AceRagState], Awaitable[AceRagState]]:
    async def execute(state: AceRagState) -> AceRagState:
        started_at = perf_counter()
        emit_event("node_start", node=name)
        try:
            update = handler(state)
            if inspect.isawaitable(update):
                update = await update
        except Exception:
            emit_event(
                "node_end",
                node=name,
                status="failed",
                duration_ms=int((perf_counter() - started_at) * 1000),
            )
            raise
        emit_event(
            "node_end",
            node=name,
            status="succeeded",
            duration_ms=int((perf_counter() - started_at) * 1000),
            **_node_result(name, update),
        )
        return update

    return execute


def _node_result(name: str, update: AceRagState) -> dict[str, object]:
    if name == "answer_evaluator":
        evaluation = update.get("answer_evaluation")
        if evaluation is not None:
            return {
                "result": {
                    "grounded": evaluation.grounded,
                    "complete": evaluation.complete,
                }
            }
    if name == "finalize_answer":
        return {
            "result": {
                "answer_status": update.get("answer_status"),
                "source_count": len(update.get("sources", [])),
            }
        }
    return {}
