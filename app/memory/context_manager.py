from __future__ import annotations

from dataclasses import dataclass

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.core.config import Settings
from app.models.llm import ChatModelService


@dataclass(frozen=True, slots=True)
class ContextWindow:
    messages: list[BaseMessage]
    conversation_summary: str | None


class ContextManager:
    def __init__(self, settings: Settings, chat_model: ChatModelService) -> None:
        self._chat_model = chat_model
        self._max_input_tokens = (
            settings.context_max_input_tokens - settings.context_reserved_output_tokens
        )

    async def build_context(
        self,
        messages: list[BaseMessage],
        conversation_summary: str | None,
        thinking_enabled: bool,
    ) -> ContextWindow:
        context_messages = self._with_summary(messages, conversation_summary)
        if self._count_tokens(context_messages, thinking_enabled) <= self._max_input_tokens:
            return ContextWindow(context_messages, conversation_summary)

        recent_messages = self._recent_messages(messages, thinking_enabled)
        retained_ids = {message.id for message in recent_messages}
        earlier_messages = [message for message in messages if message.id not in retained_ids]
        summary = await self._summarize(
            earlier_messages,
            conversation_summary,
            thinking_enabled,
        )
        return ContextWindow(self._with_summary(recent_messages, summary), summary)

    def _recent_messages(
        self,
        messages: list[BaseMessage],
        thinking_enabled: bool,
    ) -> list[BaseMessage]:
        selected: list[BaseMessage] = []
        for message in reversed(messages):
            candidate = [message, *selected]
            if selected and self._count_tokens(candidate, thinking_enabled) > self._max_input_tokens:
                break
            selected = candidate
        return selected or messages[-1:]

    async def _summarize(
        self,
        earlier_messages: list[BaseMessage],
        existing_summary: str | None,
        thinking_enabled: bool,
    ) -> str:
        transcript = "\n".join(
            f"{message.type}: {self._content(message)}" for message in earlier_messages
        )
        prompt = "\n".join(
            [
                "请用中文简洁总结以下企业知识问答的已确认上下文。",
                "只保留用户问题、已经确认的结论和引用关系；不要添加新事实。",
                f"已有摘要：{existing_summary or '无'}",
                f"待合并对话：{transcript or '无'}",
            ]
        )
        response = await self._chat_model.invoke(
            [SystemMessage(content="你负责会话摘要。"), HumanMessage(content=prompt)],
            thinking_enabled,
        )
        return self._content(response).strip()

    def _count_tokens(self, messages: list[BaseMessage], thinking_enabled: bool) -> int:
        try:
            return int(
                self._chat_model.model_for_thinking(
                    thinking_enabled
                ).get_num_tokens_from_messages(messages)
            )
        except Exception:
            return sum(max(1, len(self._content(message)) // 4) for message in messages)

    @staticmethod
    def _with_summary(
        messages: list[BaseMessage], summary: str | None
    ) -> list[BaseMessage]:
        if not summary:
            return list(messages)
        return [SystemMessage(content=f"早期会话摘要：{summary}"), *messages]

    @staticmethod
    def _content(message: BaseMessage) -> str:
        return message.text if isinstance(message.content, str) else str(message.content)
