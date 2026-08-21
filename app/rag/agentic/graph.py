from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from time import perf_counter

from langgraph.graph import END, START, StateGraph

from app.rag.agentic.nodes.context_builder import build_context
from app.rag.agentic.nodes.executor import execute_retrieval
from app.rag.agentic.nodes.grader import grade_evidence
from app.rag.agentic.nodes.planner import plan_retrieval
from app.rag.agentic.nodes.refiner import refine_retrieval
from app.rag.agentic.state import RetrievalState
from app.rag.retrieval import RetrievalService
from app.streaming.events import emit_event

Node = Callable[[RetrievalState], RetrievalState | Awaitable[RetrievalState]]


def build_retrieval_graph(
    retrieval_service: RetrievalService,
    structured: Callable,
):
    builder = StateGraph(RetrievalState)
    builder.add_node(
        "retrieval_planner",
        _tracked("retrieval_planner", lambda state: plan_retrieval(state, structured)),
    )
    builder.add_node(
        "retrieval_executor",
        _tracked(
            "retrieval_executor",
            lambda state: execute_retrieval(state, retrieval_service),
        ),
    )
    builder.add_node(
        "evidence_grader",
        _tracked("evidence_grader", lambda state: grade_evidence(state, structured)),
    )
    builder.add_node(
        "retrieval_refiner",
        _tracked("retrieval_refiner", lambda state: refine_retrieval(state, structured)),
    )
    builder.add_node("context_builder", _tracked("context_builder", build_context))

    builder.add_edge(START, "retrieval_planner")
    builder.add_edge("retrieval_planner", "retrieval_executor")
    builder.add_edge("retrieval_executor", "evidence_grader")
    builder.add_conditional_edges("evidence_grader", _route_after_grade)
    builder.add_conditional_edges("retrieval_refiner", _route_after_refiner)
    builder.add_edge("context_builder", END)
    return builder.compile()


def _route_after_grade(state: RetrievalState) -> str:
    grade = state.get("evidence_grade")
    if grade is not None and grade.sufficient:
        return "context_builder"
    if state.get("force_stop"):
        return "context_builder"
    if state.get("retrieval_round", 0) >= state.get("max_retrieval_rounds", 1):
        return "context_builder"
    return "retrieval_refiner"


def _route_after_refiner(state: RetrievalState) -> str:
    return "context_builder" if state.get("force_stop") else "retrieval_executor"


def _tracked(name: str, handler: Node) -> Callable[[RetrievalState], Awaitable[RetrievalState]]:
    async def execute(state: RetrievalState) -> RetrievalState:
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
        data: dict[str, object] = {}
        if name == "evidence_grader":
            grade = update.get("evidence_grade")
            if grade is not None:
                data["result"] = {
                    "sufficient": grade.sufficient,
                    "relevant_count": len(grade.relevant_chunk_ids),
                    "coverage_score": grade.coverage_score,
                }
        emit_event(
            "node_end",
            node=name,
            status="succeeded",
            duration_ms=int((perf_counter() - started_at) * 1000),
            **data,
        )
        return update

    return execute
