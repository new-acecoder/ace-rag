from __future__ import annotations

import asyncio

from app.rag.agentic.state import RetrievalState
from app.rag.retrieval import RetrievalService
from app.rag.schemas import RetrievedChunk

_RRF_K = 60


async def execute_retrieval(
    state: RetrievalState,
    retrieval_service: RetrievalService,
) -> RetrievalState:
    queries = state.get("current_queries", [])
    if not queries:
        return {"candidate_documents": [], "force_stop": True}

    plan = state.get("retrieval_plan")
    top_k = plan.top_k if plan is not None else state.get("requested_top_k", 1)
    ranked_lists = await asyncio.gather(
        *(retrieval_service.search(query, top_k) for query in queries)
    )
    documents = fuse_ranked_results(ranked_lists, top_k)
    return {
        "candidate_documents": documents,
        "previous_queries": _merge_queries(state.get("previous_queries", []), queries),
        "retrieval_round": state.get("retrieval_round", 0) + 1,
    }


def fuse_ranked_results(
    ranked_lists: list[list[RetrievedChunk]],
    top_k: int,
) -> list[RetrievedChunk]:
    scores: dict[tuple[str, str], float] = {}
    chunks: dict[tuple[str, str], RetrievedChunk] = {}
    first_seen: dict[tuple[str, str], int] = {}
    order = 0
    for ranked in ranked_lists:
        for rank, chunk in enumerate(ranked, start=1):
            key = (chunk.document_id, chunk.chunk_id)
            scores[key] = scores.get(key, 0.0) + 1.0 / (_RRF_K + rank)
            chunks.setdefault(key, chunk)
            if key not in first_seen:
                first_seen[key] = order
                order += 1
    ranked_keys = sorted(
        scores,
        key=lambda key: (-scores[key], first_seen[key]),
    )
    return [
        chunks[key].model_copy(update={"score": scores[key]})
        for key in ranked_keys[:top_k]
    ]


def _merge_queries(existing: list[str], incoming: list[str]) -> list[str]:
    merged = list(existing)
    seen = {query.casefold() for query in merged}
    for query in incoming:
        if query.casefold() not in seen:
            seen.add(query.casefold())
            merged.append(query)
    return merged
