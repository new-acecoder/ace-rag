from __future__ import annotations

from app.graph.services import WorkflowServices
from app.graph.state import AceRagState, RouteDecision
from app.streaming.events import emit_event


async def route_question(state: AceRagState, services: WorkflowServices) -> AceRagState:
    decision, summary = await services.structured(
        RouteDecision,
        state.get("messages", []),
        state.get("conversation_summary"),
        """判断当前问题的执行路径和必需能力，并输出 JSON。
general_chat 只适合问候、翻译、润色、普通常识和确定无需外部证据的回答，
required_capabilities 必须为空；不得用通用常识猜测特定领域的规则、阈值或触发条件。
react 适合一次或少量 Tool 调用；单一制度条款、定义、精确数值、比例、阈值、
条件、例外、产品或组合代码、以及“是否必须执行某动作”这类需要查证的问题属于 react。
这类问题即使没有明确说“知识库”或“文档”，只要答案可能依赖特定领域资料，
required_capabilities 也必须包含 knowledge；无法确认能否仅靠普适常识回答时，
优先选择 react + knowledge，不能让 general_chat 自由补充资料中的规则。
plan_execute 只适合必须拆成多个存在依赖或需要综合多个 Tool 结果的任务。
用户明确要求依据知识库、文档、上传资料、制度或内部规范时，
required_capabilities 必须包含 knowledge。
Router 不选择具体 Tool，也不生成检索 Query。
reason 只写一句简短的用户可展示原因，不要推理过程。""",
        # Routing is control-plane classification and must not change when the
        # user toggles deep thinking for the answer workflow.
        False,
    )
    route_type, capabilities = _normalize_decision(
        state.get("user_query", ""),
        decision,
    )
    emit_event(
        "route",
        route_type=route_type,
        required_capabilities=capabilities,
        reason=decision.reason[:120],
    )
    return {
        "route_type": route_type,
        "required_capabilities": capabilities,
        "conversation_summary": summary,
    }


def _normalize_decision(
    query: str,
    decision: RouteDecision,
) -> tuple[str, list[str]]:
    capabilities = list(dict.fromkeys(decision.required_capabilities))
    if _explicit_knowledge_request(query) and "knowledge" not in capabilities:
        capabilities.append("knowledge")
    route_type = decision.route_type
    if route_type == "general_chat" and capabilities:
        route_type = "react"
    elif route_type != "general_chat" and not capabilities:
        route_type = "general_chat"
    return route_type, capabilities


def _explicit_knowledge_request(query: str) -> bool:
    normalized = query.casefold()
    markers = (
        "知识库",
        "文档",
        "上传",
        "资料",
        "制度",
        "规范",
        "公司",
        "项目中",
        "手册",
        "标准",
    )
    return any(marker in normalized for marker in markers)
