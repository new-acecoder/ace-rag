from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.rag.agentic.schemas import EvidenceGrade
from app.rag.agentic.state import RetrievalState
from app.rag.schemas import RetrievedChunk
from app.streaming.events import emit_event

StructuredCall = Callable[[type[EvidenceGrade], str, bool], Awaitable[EvidenceGrade]]


async def grade_evidence(
    state: RetrievalState,
    structured: StructuredCall,
) -> RetrievalState:
    candidates = _merge_chunks(
        state.get("accepted_documents", []),
        state.get("candidate_documents", []),
    )
    if candidates:
        result = await structured(
            EvidenceGrade,
            "\n".join(
                [
                    "只判断当前证据是否足以完成知识目标，并只输出 JSON。",
                    "不得回答用户问题。relevant_chunk_ids 只能选择给定的真实 "
                    "chunk_id。",
                    "sufficient 只有在证据覆盖目标所需事实且不存在未解决冲突时"
                    "才能为 true。",
                    "next_action 在充分时必须为 answer；不足时选择 rewrite、"
                    "multi_query、decompose 或 continue_search。",
                    f"原始查询：{state.get('original_query', '')}",
                    f"知识目标：{state.get('goal', '')}",
                    f"已使用 Query：{state.get('previous_queries', [])}",
                    f"证据：{_evidence_text(candidates)}",
                ]
            ),
            state.get("thinking_enabled", False),
        )
    else:
        result = EvidenceGrade(
            relevant=False,
            sufficient=False,
            coverage_score=0.0,
            relevant_chunk_ids=[],
            missing_information=["知识库未返回相关资料"],
            conflicts=[],
            next_action="continue_search",
            reason="当前检索没有返回可评估证据",
        )

    by_id = {chunk.chunk_id: chunk for chunk in candidates}
    relevant_ids = [
        chunk_id
        for chunk_id in dict.fromkeys(result.relevant_chunk_ids)
        if chunk_id in by_id
    ]
    sufficient = bool(result.sufficient and relevant_ids and not result.conflicts)
    normalized = result.model_copy(
        update={
            "relevant": bool(relevant_ids),
            "sufficient": sufficient,
            "relevant_chunk_ids": relevant_ids,
            "next_action": "answer" if sufficient else (
                "continue_search" if result.next_action == "answer" else result.next_action
            ),
        }
    )
    accepted = _merge_chunks(
        state.get("accepted_documents", []),
        [by_id[chunk_id] for chunk_id in relevant_ids],
    )
    current_queries = state.get("current_queries", [])
    emit_event(
        "retrieval",
        query=current_queries[0] if current_queries else state.get("original_query", ""),
        queries=current_queries,
        strategy=state.get("current_strategy", "single"),
        round=state.get("retrieval_round", 0),
        result_count=len(state.get("candidate_documents", [])),
        relevant_count=len(relevant_ids),
    )
    return {
        "evidence_grade": normalized,
        "accepted_documents": accepted,
        "evidence_insufficient": not sufficient,
    }


def _merge_chunks(
    existing: list[RetrievedChunk],
    incoming: list[RetrievedChunk],
) -> list[RetrievedChunk]:
    merged = {(chunk.document_id, chunk.chunk_id): chunk for chunk in existing}
    for chunk in incoming:
        merged.setdefault((chunk.document_id, chunk.chunk_id), chunk)
    return list(merged.values())


def _evidence_text(chunks: list[RetrievedChunk]) -> str:
    return "\n\n".join(
        f"chunk_id={chunk.chunk_id}\n标题={chunk.title}\n内容={chunk.content}"
        for chunk in chunks
    )
