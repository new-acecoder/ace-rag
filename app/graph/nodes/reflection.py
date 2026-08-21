from __future__ import annotations

from app.graph.nodes.common import evidence_text
from app.graph.services import WorkflowServices
from app.graph.state import AceRagState, ReflectionDecision


async def reflect_on_answer(
    state: AceRagState,
    services: WorkflowServices,
) -> AceRagState:
    evaluation = state.get("answer_evaluation")
    if evaluation is None:
        raise ValueError("answer_evaluation is required before reflection")
    decision, summary = await services.structured(
        ReflectionDecision,
        state.get("messages", []),
        state.get("conversation_summary"),
        "\n".join(
            [
                "判断候选答案失败的根因，并只输出 JSON。",
                "retrieval_insufficient 表示证据本身不足，next_action=retrieve_again；",
                "generation_error 表示证据足够但答案使用错误，"
                "next_action=regenerate；",
                "query_misunderstood 表示原问题或任务目标理解错误，"
                "next_action=replan。",
                "不要生成答案或检索 Query。",
                f"原始问题：{state.get('user_query', '')}",
                f"候选答案：{state.get('draft_answer', '')}",
                f"评估缺失：{evaluation.missing_aspects}",
                f"证据：{evidence_text(state.get('retrieved_chunks', []))}",
            ]
        ),
        services.thinking_enabled(state),
    )
    decision = _normalize_decision(decision)
    update: AceRagState = {
        "reflection_decision": decision,
        "reflection_count": state.get("reflection_count", 0) + 1,
        "answer_status": None,
        "conversation_summary": summary,
    }
    if decision.next_action != "regenerate":
        update.update(
            {
                "draft_answer": None,
                "cited_chunk_ids": [],
                "answer_evaluation": None,
            }
        )
    if decision.next_action == "retrieve_again":
        update["current_query"] = " ".join(
            [
                state.get("user_query", "").strip(),
                *[item.strip() for item in evaluation.missing_aspects if item.strip()],
            ]
        ).strip()
    elif decision.next_action == "replan" and state.get("route_type") == "react":
        update["current_query"] = state.get("user_query", "").strip()
    return update


def _normalize_decision(decision: ReflectionDecision) -> ReflectionDecision:
    expected = {
        "retrieval_insufficient": "retrieve_again",
        "generation_error": "regenerate",
        "query_misunderstood": "replan",
    }[decision.failure_type]
    return decision.model_copy(update={"next_action": expected})
