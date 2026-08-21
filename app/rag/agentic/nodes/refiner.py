from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.rag.agentic.nodes.planner import normalize_queries
from app.rag.agentic.schemas import RetrievalRefinement
from app.rag.agentic.state import RetrievalState
from app.streaming.events import emit_event

StructuredCall = Callable[
    [type[RetrievalRefinement], str, bool],
    Awaitable[RetrievalRefinement],
]


async def refine_retrieval(
    state: RetrievalState,
    structured: StructuredCall,
) -> RetrievalState:
    grade = state.get("evidence_grade")
    result = await structured(
        RetrievalRefinement,
        "\n".join(
            [
                "根据证据缺口生成下一轮知识库检索 Query，并只输出 JSON。",
                "action 只能是 rewrite、multi_query、decompose、next_hop。",
                "next_hop 必须基于现有证据中已确认的实体；不要回答问题。",
                f"原始查询：{state.get('original_query', '')}",
                f"知识目标：{state.get('goal', '')}",
                f"历史 Query：{state.get('previous_queries', [])}",
                f"缺失信息：{grade.missing_information if grade else []}",
                f"证据冲突：{grade.conflicts if grade else []}",
                f"最多新 Query 数：{state.get('max_queries_per_round', 1)}",
                f"已接受证据摘要：{_accepted_evidence(state)}",
            ]
        ),
        state.get("thinking_enabled", False),
    )
    queries = normalize_queries(
        result.queries,
        state.get("max_queries_per_round", 1),
    )
    previous = {query.casefold() for query in state.get("previous_queries", [])}
    queries = [query for query in queries if query.casefold() not in previous]
    if result.action == "rewrite":
        queries = queries[:1]

    if queries and result.action in {"rewrite", "next_hop"}:
        emit_event(
            "rewrite",
            previous_query=(state.get("current_queries", [""]) or [""])[0],
            rewritten_query=queries[0],
            missing_aspects=grade.missing_information if grade else [],
        )
    return {
        "refinement": result.model_copy(update={"queries": queries}),
        "current_strategy": result.action,
        "current_queries": queries,
        "candidate_documents": [],
        "force_stop": not queries,
    }


def _accepted_evidence(state: RetrievalState) -> str:
    chunks = state.get("accepted_documents", [])
    if not chunks:
        return "无"
    return "\n".join(
        f"chunk_id={chunk.chunk_id}: {chunk.content[:400]}" for chunk in chunks
    )
