from __future__ import annotations

from langchain_core.messages import AIMessage

from app.graph.state import AceRagState
from app.rag.schemas import Source


def finalize_answer(state: AceRagState) -> AceRagState:
    turn_id = state.get("turn_id")
    draft_answer = state.get("draft_answer")
    answer_status = state.get("answer_status")
    if not turn_id:
        raise ValueError("turn_id is required")
    if not draft_answer:
        raise ValueError("draft_answer is required")
    if answer_status not in {"accepted", "best_effort"}:
        raise ValueError("answer_status must be accepted or best_effort")

    chunks_by_id = {
        chunk.chunk_id: chunk for chunk in state.get("retrieved_chunks", [])
    }
    sources: list[Source] = []
    cited_chunk_ids: set[str] = set()
    for chunk_id in state.get("cited_chunk_ids", []):
        if chunk_id in cited_chunk_ids:
            continue
        cited_chunk_ids.add(chunk_id)
        chunk = chunks_by_id.get(chunk_id)
        if chunk is None:
            raise ValueError("cited_chunk_ids must belong to retrieved_chunks")
        sources.append(
            Source(
                citation_index=len(sources) + 1,
                document_id=chunk.document_id,
                chunk_id=chunk.chunk_id,
                title=chunk.title,
                page_number=chunk.page_number,
                source=chunk.source,
                document_type=chunk.document_type,
            )
        )

    message = AIMessage(
        id=f"{turn_id}:assistant",
        content=draft_answer,
        additional_kwargs={
            "turn_id": turn_id,
            "answer_status": answer_status,
            "sources": [source.model_dump(mode="json") for source in sources],
        },
    )
    return {
        "messages": [message],
        "sources": sources,
        "answer_status": answer_status,
    }
