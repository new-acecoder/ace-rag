from __future__ import annotations

from typing import TypeVar

from langchain_core.messages import BaseMessage, SystemMessage
from pydantic import BaseModel

from app.agents.react_agent import build_react_agent
from app.core.config import Settings
from app.memory.context_manager import ContextManager
from app.models.llm import ChatModelService
from app.rag.agentic.runner import AgenticRetrievalRunner
from app.rag.retrieval import RetrievalService
from app.tools.knowledge import build_knowledge_registry
from app.tools.registry import ToolRegistry
from app.tools.types import ToolCapability

StructuredResponse = TypeVar("StructuredResponse", bound=BaseModel)


class WorkflowServices:
    def __init__(
        self,
        settings: Settings,
        chat_model: ChatModelService,
        context_manager: ContextManager,
        retrieval_service: RetrievalService,
    ) -> None:
        self.settings = settings
        self.chat_model = chat_model
        self.context_manager = context_manager
        self.retrieval_service = retrieval_service
        self.agentic_retrieval = AgenticRetrievalRunner(
            settings,
            chat_model,
            context_manager,
            retrieval_service,
        )
        self._tool_registries: dict[bool, ToolRegistry] = {}
        self._react_agents: dict[tuple[bool, tuple[ToolCapability, ...]], object] = {}

    def thinking_enabled(self, state: dict[str, object]) -> bool:
        value = state.get("thinking_enabled")
        return value if isinstance(value, bool) else self.settings.chat_thinking_enabled

    def tool_registry(self, thinking_enabled: bool) -> ToolRegistry:
        if thinking_enabled not in self._tool_registries:
            self._tool_registries[thinking_enabled] = build_knowledge_registry(
                self.retrieval_service,
                self.agentic_retrieval,
                thinking_enabled,
            )
        return self._tool_registries[thinking_enabled]

    def react_agent(
        self,
        thinking_enabled: bool,
        capabilities: tuple[ToolCapability, ...],
    ):
        key = (thinking_enabled, capabilities)
        if key not in self._react_agents:
            tools = self.tool_registry(thinking_enabled).tools_for(capabilities)
            self._react_agents[key] = build_react_agent(
                self.chat_model.model_for_thinking(thinking_enabled),
                tools,
                self.settings,
            )
        return self._react_agents[key]

    async def structured(
        self,
        schema: type[StructuredResponse],
        messages: list[BaseMessage],
        conversation_summary: str | None,
        instruction: str,
        thinking_enabled: bool,
    ) -> tuple[StructuredResponse, str | None]:
        context = await self.context_manager.build_context(
            messages,
            conversation_summary,
            thinking_enabled,
        )
        result = await self.chat_model.structured(
            schema,
            [SystemMessage(content=instruction), *context.messages],
            thinking_enabled,
        )
        return result, context.conversation_summary
