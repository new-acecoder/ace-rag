from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.rag.agentic.schemas import RetrievalPlan
from app.rag.agentic.state import RetrievalState

StructuredCall = Callable[[type[RetrievalPlan], str, bool], Awaitable[RetrievalPlan]]


async def plan_retrieval(
    state: RetrievalState,
    structured: StructuredCall,
) -> RetrievalState:
    original_query = state.get("original_query", "").strip()
    goal = state.get("goal", "").strip() or original_query
    if not original_query:
        raise ValueError("original_query is required")

    result = await structured(
        RetrievalPlan,
        "\n".join(
            [
                "为当前知识目标制定检索计划，并只输出 JSON。",
                "strategy 只能是 single、rewrite、multi_query、decompose。",
                "single/rewrite 只生成一个 query；multi_query/decompose 可以生成"
                "多条互补 query。",
                "decompose 只拆搜索 query，不创建业务任务步骤。",
                "不要回答问题，不要选择向量库、Dense/BM25 或 RRF 参数。",
                f"原始查询：{original_query}",
                f"当前知识目标：{goal}",
                f"最多 Query 数：{state.get('max_queries_per_round', 1)}",
                f"系统允许的最大 top_k：{state.get('requested_top_k', 1)}",
            ]
        ),
        state.get("thinking_enabled", False),
    )
    queries = _normalize_queries(
        result.queries,
        state.get("max_queries_per_round", 1),
    )
    if not queries:
        queries = [original_query]
    if result.strategy in {"single", "rewrite"}:
        queries = queries[:1]

    normalized = result.model_copy(
        update={
            "queries": queries,
            "top_k": min(result.top_k, state.get("requested_top_k", 1)),
        }
    )
    return {
        "retrieval_plan": normalized,
        "current_strategy": normalized.strategy,
        "current_queries": normalized.queries,
    }


def normalize_queries(queries: list[str], limit: int) -> list[str]:
    return _normalize_queries(queries, limit)


def _normalize_queries(queries: list[str], limit: int) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for query in queries:
        value = query.strip()
        key = value.casefold()
        if not value or key in seen:
            continue
        seen.add(key)
        normalized.append(value)
        if len(normalized) >= limit:
            break
    return normalized
