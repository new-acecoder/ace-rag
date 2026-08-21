from __future__ import annotations

from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage, HumanMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from app.rag.agentic.schemas import EvidenceGrade
from app.rag.schemas import RetrievedChunk, Source
from app.tools.types import ToolCapability


class PlanStep(BaseModel):
    step_id: int
    goal: str
    search_query: str


class Plan(BaseModel):
    steps: list[PlanStep]


class StepResult(BaseModel):
    step_id: int
    evidence: list[RetrievedChunk]


class RetrievalGrade(BaseModel):
    """Legacy checkpoint schema retained for completed V1 conversations."""

    relevant: bool
    sufficient: bool
    relevant_chunk_ids: list[str]
    missing_aspects: list[str]


class AnswerEvaluation(BaseModel):
    grounded: bool
    complete: bool
    missing_aspects: list[str]


class RouteDecision(BaseModel):
    route_type: Literal["general_chat", "react", "plan_execute"]
    required_capabilities: list[ToolCapability] = Field(default_factory=list)
    reason: str


class ReplanDecision(BaseModel):
    action: Literal["continue", "revise", "finish"]
    revised_steps: list[PlanStep]
    reason: str


class GeneratedAnswer(BaseModel):
    draft_answer: str
    cited_chunk_ids: list[str]


class ReflectionDecision(BaseModel):
    failure_type: Literal[
        "retrieval_insufficient",
        "generation_error",
        "query_misunderstood",
    ]
    next_action: Literal["retrieve_again", "regenerate", "replan"]
    reason: str


class AceRagState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    conversation_summary: str | None

    turn_id: str
    user_query: str
    thinking_enabled: bool

    route_type: Literal["general_chat", "react", "plan_execute"] | None
    required_capabilities: list[ToolCapability]

    current_query: str
    rewritten_query: str | None

    plan: list[PlanStep]
    current_step_index: int
    completed_steps: list[StepResult]
    intermediate_results: list[StepResult]

    retrieval_batch: list[RetrievedChunk]
    retrieved_chunks: list[RetrievedChunk]
    retrieval_grade: EvidenceGrade | RetrievalGrade | None
    evidence_insufficient: bool
    queries_used: list[str]

    draft_answer: str | None
    cited_chunk_ids: list[str]
    sources: list[Source]
    generation_mode: Literal["normal", "best_effort"]
    answer_status: Literal["accepted", "best_effort"] | None

    answer_evaluation: AnswerEvaluation | None
    reflection_decision: ReflectionDecision | None

    rewrite_count: int
    replan_count: int
    reflection_count: int
    retrieval_count: int

    error: str | None


def new_turn_input(
    turn_id: str,
    user_query: str,
    thinking_enabled: bool = True,
) -> AceRagState:
    return {
        "messages": [HumanMessage(id=f"{turn_id}:user", content=user_query)],
        "turn_id": turn_id,
        "user_query": user_query,
        "thinking_enabled": thinking_enabled,
    }


def conversation_config(conversation_id: str) -> dict[str, dict[str, str]]:
    return {"configurable": {"thread_id": conversation_id}}
