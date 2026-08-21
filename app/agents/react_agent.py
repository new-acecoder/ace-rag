from __future__ import annotations

import json

from langchain.agents import create_agent
from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ToolCallLimitMiddleware,
    wrap_tool_call,
)
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.agents.state import ReactPrivateState
from app.core.config import Settings


class ReactAnswer(BaseModel):
    draft_answer: str
    cited_chunk_ids: list[str]


@wrap_tool_call
async def recover_invalid_tool_arguments(request, handler):
    try:
        return await handler(request)
    except ValueError as error:
        return ToolMessage(
            content=(
                f"Tool 参数无效：{error}。"
                "请不要重复这个调用；改用有效的检索结果，或说明现有资料不足。"
            ),
            tool_call_id=request.tool_call["id"],
            name=request.tool_call["name"],
            status="error",
        )


def build_react_agent(
    model: ChatOpenAI,
    tools: list[BaseTool],
    settings: Settings,
):
    return create_agent(
        # DeepSeek thinking mode accepts ordinary tool calls and JSON Mode, but
        # rejects the forced tool_choice used by ToolStrategy.
        model=model.bind(response_format={"type": "json_object"}),
        tools=tools,
        system_prompt=(
            "你是 Ace RAG Tool Agent。根据本轮能力约束，从已注入的 Tool 中选择完成任务所需的能力。"
            "是否必须调用知识库由本轮私有 SystemMessage 指定，不得自行绕过能力约束。"
            "知识库的查询改写、多查询和多跳检索由 search_knowledge_base 内部完成；"
            "同一知识目标最多调用一次 search_knowledge_base，不得用同义词重复调用。"
            "get_document_context 和 get_document_info 只能作为已有知识搜索结果的补充。"
            "只能引用 Tool artifact 中真实的 chunk_id；无法确认时明确说明证据不足。"
            "最终 draft_answer 必须逐项覆盖原始问题明确要求的数值、条件、例外与子结论；"
            "对错误前提必须先明确纠正，再给出资料中的对应事实。"
            "完成所有 Tool 调用后，最终回复必须只返回符合以下 JSON Schema 的 JSON 对象："
            f"{json.dumps(ReactAnswer.model_json_schema(), ensure_ascii=False)}"
        ),
        state_schema=ReactPrivateState,
        middleware=[
            recover_invalid_tool_arguments,
            ToolCallLimitMiddleware(
                run_limit=settings.react_max_tool_calls,
                exit_behavior="end",
            ),
            ModelCallLimitMiddleware(run_limit=settings.react_max_model_calls),
        ],
        name="ace_react",
    )
