from __future__ import annotations

from app.graph.nodes.common import evidence_text, insufficient_evidence_answer
from app.graph.services import WorkflowServices
from app.graph.state import AceRagState, GeneratedAnswer


async def generate_answer(state: AceRagState, services: WorkflowServices) -> AceRagState:
    chunks = state.get("retrieved_chunks", [])
    if not chunks:
        return {
            "draft_answer": insufficient_evidence_answer(),
            "cited_chunk_ids": [],
            "generation_mode": "best_effort",
            "answer_status": "best_effort",
        }

    result, summary = await services.structured(
        GeneratedAnswer,
        state.get("messages", []),
        state.get("conversation_summary"),
        "\n".join(
            [
                "只基于已认可的企业知识库证据生成答案，并输出 JSON。",
                "draft_answer 中的 [1]...[n] 必须按 cited_chunk_ids 的顺序引用真实 chunk_id。",
                "不要编造未在证据中出现的企业事实或来源。",
                f"回答模式：{state.get('generation_mode', 'normal')}",
                f"原始问题：{state.get('user_query', '')}",
                f"已完成计划：{[result.step_id for result in state.get('completed_steps', [])]}",
                f"证据：{evidence_text(chunks)}",
                ]
            ),
        services.thinking_enabled(state),
    )
    return {
        "draft_answer": result.draft_answer,
        "cited_chunk_ids": result.cited_chunk_ids,
        "conversation_summary": summary,
    }
