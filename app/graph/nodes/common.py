from __future__ import annotations

import re

from app.graph.state import AceRagState, PlanStep
from app.rag.schemas import RetrievedChunk

_CITATION_PATTERN = re.compile(r"\[(\d+)\]")


def evidence_text(chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return "无有效证据。"
    return "\n\n".join(
        f"chunk_id={chunk.chunk_id}\n标题={chunk.title}\n内容={chunk.content}"
        for chunk in chunks
    )


def merge_chunks(
    existing: list[RetrievedChunk],
    incoming: list[RetrievedChunk],
) -> list[RetrievedChunk]:
    merged = {(chunk.document_id, chunk.chunk_id): chunk for chunk in existing}
    for chunk in incoming:
        merged.setdefault((chunk.document_id, chunk.chunk_id), chunk)
    return list(merged.values())


def current_plan_step(state: AceRagState) -> PlanStep:
    plan = state.get("plan", [])
    index = state.get("current_step_index", 0)
    if not 0 <= index < len(plan):
        raise ValueError("current plan step is unavailable")
    return plan[index]


def pending_steps(state: AceRagState) -> list[PlanStep]:
    completed_ids = {result.step_id for result in state.get("completed_steps", [])}
    return [step for step in state.get("plan", []) if step.step_id not in completed_ids]


def citations_match_answer(answer: str, cited_chunk_ids: list[str]) -> bool:
    citations = [int(value) for value in _CITATION_PATTERN.findall(answer)]
    if not cited_chunk_ids:
        return not citations
    if not citations or any(index < 1 or index > len(cited_chunk_ids) for index in citations):
        return False
    first_seen: list[int] = []
    for index in citations:
        if index not in first_seen:
            first_seen.append(index)
    return first_seen == list(range(1, len(cited_chunk_ids) + 1))


def insufficient_evidence_answer() -> str:
    return "当前知识库暂无足够信息，无法基于现有资料给出可靠回答。"
