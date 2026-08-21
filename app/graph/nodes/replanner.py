from __future__ import annotations

from app.graph.nodes.common import pending_steps
from app.graph.services import WorkflowServices
from app.graph.state import AceRagState, PlanStep, ReplanDecision
from app.streaming.events import emit_event


async def replan(state: AceRagState, services: WorkflowServices) -> AceRagState:
    pending = pending_steps(state)
    decision, summary = await services.structured(
        ReplanDecision,
        state.get("messages", []),
        state.get("conversation_summary"),
        "\n".join(
            [
                "根据现有执行结果决定企业知识库检索计划下一步，并输出 JSON。",
                "continue 表示按当前剩余 Step 继续，revised_steps 必须为空；",
                "revise 只能给出新的完整 Pending 检索 Step 列表；",
                "finish 只能在所有 Step 已完成时使用，revised_steps 必须为空。",
                f"原始问题：{state.get('user_query', '')}",
                f"已完成 Step：{[result.step_id for result in state.get('completed_steps', [])]}",
                f"剩余 Step：{[step.model_dump() for step in pending]}",
                f"缺失方面：{_missing_aspects(state)}",
                ]
            ),
            services.thinking_enabled(state),
    )
    plan, replan_count = _apply_replan(state, decision, services.settings.max_plan_steps)
    remaining = _remaining_steps(plan, state.get("completed_steps", []))
    emit_event(
        "replan",
        action=decision.action,
        remaining_steps=[step.model_dump() for step in remaining],
        reason=decision.reason[:120],
    )
    return {
        "plan": plan,
        "replan_count": replan_count,
        "conversation_summary": summary,
    }


def _apply_replan(
    state: AceRagState,
    decision: ReplanDecision,
    max_plan_steps: int,
) -> tuple[list[PlanStep], int]:
    plan = state.get("plan", [])
    completed_ids = {result.step_id for result in state.get("completed_steps", [])}
    pending = [step for step in plan if step.step_id not in completed_ids]

    if decision.action == "continue":
        if decision.revised_steps or not pending:
            raise ValueError("invalid continue replan decision")
        return plan, state.get("replan_count", 0)
    if decision.action == "finish":
        if decision.revised_steps or pending:
            raise ValueError("finish requires all plan steps to be completed")
        return plan, state.get("replan_count", 0)

    revised = decision.revised_steps
    if not revised:
        raise ValueError("revise requires pending retrieval steps")
    if len(completed_ids) + len(revised) > max_plan_steps:
        raise ValueError("revised plan exceeds MAX_PLAN_STEPS")
    revised_ids = [step.step_id for step in revised]
    if len(revised_ids) != len(set(revised_ids)):
        raise ValueError("revised plan step_ids must be unique")
    max_existing_id = max((step.step_id for step in plan), default=0)
    pending_ids = {step.step_id for step in pending}
    for step in revised:
        if not step.goal.strip() or not step.search_query.strip():
            raise ValueError("revised plan steps must include a goal and search_query")
        if step.step_id in completed_ids or (
            step.step_id not in pending_ids and step.step_id <= max_existing_id
        ):
            raise ValueError("revised plan cannot modify completed steps")
    completed = [step for step in plan if step.step_id in completed_ids]
    return [*completed, *revised], state.get("replan_count", 0) + 1


def _remaining_steps(plan: list[PlanStep], completed_steps: list[object]) -> list[PlanStep]:
    completed_ids = {getattr(step, "step_id") for step in completed_steps}
    return [step for step in plan if step.step_id not in completed_ids]


def _missing_aspects(state: AceRagState) -> list[str]:
    evaluation = state.get("answer_evaluation")
    if evaluation is not None:
        return evaluation.missing_aspects
    grade = state.get("retrieval_grade")
    return grade.missing_aspects if grade is not None else []
