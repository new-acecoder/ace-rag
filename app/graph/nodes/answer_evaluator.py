from __future__ import annotations

from app.graph.nodes.common import citations_match_answer, evidence_text
from app.graph.services import WorkflowServices
from app.graph.state import AceRagState, AnswerEvaluation


async def evaluate_answer(state: AceRagState, services: WorkflowServices) -> AceRagState:
    draft_answer = state.get("draft_answer")
    if not draft_answer:
        raise ValueError("draft_answer is required before evaluation")
    cited_chunk_ids = state.get("cited_chunk_ids", [])
    if not citations_match_answer(draft_answer, cited_chunk_ids):
        evaluation = AnswerEvaluation(
            grounded=False,
            complete=False,
            missing_aspects=["答案中的引用标记与 cited_chunk_ids 不一致"],
        )
        summary = state.get("conversation_summary")
    else:
        evaluation, summary = await services.structured(
            AnswerEvaluation,
            state.get("messages", []),
            state.get("conversation_summary"),
            "\n".join(
                [
                    "评估候选答案是否只依据企业知识库证据且覆盖用户问题，并输出 JSON。",
                    "grounded 判断核心事实是否由证据支持；complete 判断问题及已完成计划目标是否覆盖。",
                    "只有明确回答问题中的每个结论、数值、条件和例外时，complete 才能为 true；"
                    "是非或纠错问题必须明确给出肯定或否定，不能只罗列背景。"
                    "文档外问题必须明确说明现有资料无法回答，不能补充外部事实。",
                    f"原始问题：{state.get('user_query', '')}",
                    f"候选答案：{draft_answer}",
                    f"cited_chunk_ids：{cited_chunk_ids}",
                    f"已完成 Step：{[result.step_id for result in state.get('completed_steps', [])]}",
                    f"回答模式：{state.get('generation_mode', 'normal')}",
                    f"证据：{evidence_text(state.get('retrieved_chunks', []))}",
                ]
            ),
            services.thinking_enabled(state),
        )

    accepted = evaluation.grounded and (
        evaluation.complete or state.get("generation_mode") == "best_effort"
    )
    answer_status = (
        "best_effort"
        if accepted and state.get("generation_mode") == "best_effort"
        else "accepted"
        if accepted
        else None
    )
    return {
        "answer_evaluation": evaluation,
        "answer_status": answer_status,
        "conversation_summary": summary,
    }
