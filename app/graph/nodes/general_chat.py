from __future__ import annotations

from langchain_core.messages import SystemMessage

from app.graph.services import WorkflowServices
from app.graph.state import AceRagState


async def answer_general_chat(
    state: AceRagState,
    services: WorkflowServices,
) -> AceRagState:
    thinking_enabled = services.thinking_enabled(state)
    context = await services.context_manager.build_context(
        state.get("messages", []),
        state.get("conversation_summary"),
        thinking_enabled,
    )
    response = await services.chat_model.invoke(
        [
            SystemMessage(
                content=(
                    "你是 Ace RAG 助手。当前问题不需要外部 Tool，"
                    "直接自然、准确地回答。"
                    "可以进行闲聊、翻译、润色、常识解释和简单推理；"
                    "不要声称查询了知识库，也不要生成文档引用标记。"
                )
            ),
            *context.messages,
        ],
        thinking_enabled,
    )
    answer = response.text.strip()
    if not answer:
        raise ValueError("general chat model returned an empty answer")
    return {
        "draft_answer": answer,
        "cited_chunk_ids": [],
        "retrieved_chunks": [],
        "answer_status": "accepted",
        "conversation_summary": context.conversation_summary,
    }
