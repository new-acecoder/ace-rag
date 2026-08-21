from __future__ import annotations

import json
from typing import TypeVar

from langchain_core.messages import BaseMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.core.config import Settings
from app.core.errors import ServiceUnavailableError

StructuredResponse = TypeVar("StructuredResponse", bound=BaseModel)


class ChatModelService:
    def __init__(self, settings: Settings) -> None:
        api_key = settings.chat_model_api_key
        if api_key is None:
            raise ServiceUnavailableError("Chat 模型")

        self._model_options = {
            "model": settings.chat_model_name,
            "api_key": api_key.get_secret_value(),
            "base_url": settings.chat_model_base_url,
            "temperature": 0,
        }
        self._default_thinking_enabled = settings.chat_thinking_enabled
        self._models: dict[bool, ChatOpenAI] = {}

    @property
    def model(self) -> ChatOpenAI:
        return self.model_for_thinking(self._default_thinking_enabled)

    def model_for_thinking(self, thinking_enabled: bool) -> ChatOpenAI:
        if thinking_enabled not in self._models:
            self._models[thinking_enabled] = ChatOpenAI(
                **self._model_options,
                extra_body={
                    "thinking": {"type": "enabled" if thinking_enabled else "disabled"}
                },
            )
        return self._models[thinking_enabled]

    async def invoke(
        self,
        messages: list[BaseMessage],
        thinking_enabled: bool,
    ) -> BaseMessage:
        try:
            return await self.model_for_thinking(thinking_enabled).ainvoke(messages)
        except Exception as error:
            raise ServiceUnavailableError("Chat 模型") from error

    async def structured(
        self,
        schema: type[StructuredResponse],
        messages: list[BaseMessage],
        thinking_enabled: bool,
    ) -> StructuredResponse:
        structured_model = self.model_for_thinking(thinking_enabled).with_structured_output(
            schema,
            method="json_mode",
        )
        try:
            result = await structured_model.ainvoke(
                [
                    SystemMessage(
                        content="\n".join(
                            [
                                "必须只返回符合以下 JSON Schema 的 JSON 对象，不要返回额外文字。",
                                json.dumps(schema.model_json_schema(), ensure_ascii=False),
                            ]
                        )
                    ),
                    *messages,
                ]
            )
        except Exception as error:
            raise ServiceUnavailableError("Chat 模型") from error

        if isinstance(result, schema):
            return result
        try:
            return schema.model_validate(result)
        except Exception as error:
            raise ServiceUnavailableError("Chat 模型") from error
