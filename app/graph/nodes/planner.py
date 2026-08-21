from __future__ import annotations

from app.graph.services import WorkflowServices
from app.graph.state import AceRagState, Plan, PlanStep
from app.streaming.events import emit_event


async def plan_question(state: AceRagState, services: WorkflowServices) -> AceRagState:
    plan, summary = await services.structured(
        Plan,
        state.get("messages", []),
        state.get("conversation_summary"),
        """为原始用户问题制定企业知识库证据检索计划，并输出 JSON。
每个 Step 只能是可执行的资料检索目标，包含从 1 开始递增的 step_id、goal、search_query。
禁止“汇总”“比较结论”“生成答案”等非检索步骤，最多 5 步。""",
        services.thinking_enabled(state),
    )
    steps = _validate_initial_plan(plan.steps, services.settings.max_plan_steps)
    emit_event(
        "plan",
        steps=[step.model_dump() for step in steps],
    )
    return {
        "plan": steps,
        "current_step_index": 0,
        "conversation_summary": summary,
    }


def _validate_initial_plan(steps: list[PlanStep], max_steps: int) -> list[PlanStep]:
    if not steps or len(steps) > max_steps:
        raise ValueError("plan must contain between 1 and MAX_PLAN_STEPS steps")
    expected_ids = list(range(1, len(steps) + 1))
    if [step.step_id for step in steps] != expected_ids:
        raise ValueError("plan step_ids must start at 1 and increase monotonically")
    if any(not step.goal.strip() or not step.search_query.strip() for step in steps):
        raise ValueError("plan steps must include a goal and search_query")
    return steps
