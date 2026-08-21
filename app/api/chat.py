from __future__ import annotations

import asyncio
from contextlib import suppress
from collections.abc import AsyncIterator
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from pydantic import BaseModel, field_validator

from app.core.config import get_settings
from app.core.errors import (
    ConversationNotFoundError,
    ServiceUnavailableError,
    TurnAlreadyCompletedError,
    TurnRequiresResumeError,
)
from app.graph.state import conversation_config, new_turn_input
from app.rag.schemas import Source
from app.runtime.run_registry import ActiveRun, ConversationRunRegistry
from app.streaming.sse import SseEventEncoder

router = APIRouter(prefix="/api/v1", tags=["chat"])


class ChatStreamRequest(BaseModel):
    conversation_id: UUID
    turn_id: UUID
    message: str
    thinking_enabled: bool | None = None

    @field_validator("message")
    @classmethod
    def message_cannot_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message cannot be blank")
        return value


class ConversationMessage(BaseModel):
    id: str
    turn_id: str
    role: Literal["user", "assistant"]
    content: str
    answer_status: Literal["accepted", "best_effort"] | None = None
    sources: list[Source] | None = None


class ConversationResponse(BaseModel):
    conversation_id: str
    messages: list[ConversationMessage]
    active_turn_id: str | None
    resumable_turn_id: str | None


class ChatRuntime:
    def __init__(self, graph: Any, registry: ConversationRunRegistry) -> None:
        self._graph = graph
        self._registry = registry

    async def begin_new_turn(
        self,
        conversation_id: str,
        turn_id: str,
    ) -> ActiveRun:
        await self._validate_new_turn(conversation_id, turn_id)
        return await self._registry.acquire(conversation_id, turn_id)

    async def begin_resume(
        self,
        conversation_id: str,
        turn_id: str,
    ) -> ActiveRun:
        await self._validate_resume(conversation_id, turn_id)
        return await self._registry.acquire(conversation_id, turn_id)

    async def stream(
        self,
        request: Request,
        run: ActiveRun,
        message: str | None,
        resumed: bool,
        thinking_enabled: bool = True,
    ) -> AsyncIterator[bytes]:
        encoder = SseEventEncoder(
            conversation_id=run.conversation_id,
            turn_id=run.turn_id,
            run_id=run.run_id,
        )
        terminal_sent = False
        try:
            yield encoder.encode("start", resumed=resumed)
            graph_input = (
                None
                if resumed
                else new_turn_input(
                    run.turn_id,
                    message or "",
                    thinking_enabled=thinking_enabled,
                )
            )
            config = {
                **conversation_config(run.conversation_id),
                "recursion_limit": 80,
                "metadata": {
                    "conversation_id": run.conversation_id,
                    "turn_id": run.turn_id,
                    "run_id": run.run_id,
                },
            }
            async for event in self._graph_events(graph_input, config, request):
                parsed = _graph_event(event)
                if parsed is not None:
                    event_name, data = parsed
                    yield encoder.encode(event_name, **data)

            final_message = await self._final_message(run.conversation_id, run.turn_id)
            if final_message is None:
                raise RuntimeError("parent graph completed without a final assistant message")
            if await request.is_disconnected():
                return
            for content in _answer_chunks(_message_content(final_message)):
                if await request.is_disconnected():
                    return
                yield encoder.encode("token", content=content)
            for source in _message_sources(final_message):
                if await request.is_disconnected():
                    return
                yield encoder.encode("source", **source.model_dump(mode="json"))
            answer_status = final_message.additional_kwargs.get("answer_status")
            yield encoder.encode(
                "done",
                message_id=final_message.id,
                answer_status=answer_status,
            )
            terminal_sent = True
        except asyncio.CancelledError:
            raise
        except Exception as error:
            if not await request.is_disconnected() and not terminal_sent:
                code, safe_message = _stream_error(error)
                yield encoder.encode(
                    "error",
                    code=code,
                    message=safe_message,
                    resumable=await self._is_resumable(run.conversation_id, run.turn_id),
                )
        finally:
            await self._registry.release(run)

    async def history(self, conversation_id: str) -> ConversationResponse:
        active = await self._registry.get(conversation_id)
        values = await self._state_values(conversation_id)
        messages = _public_messages(values.get("messages", []))
        resumable_turn_id = None
        if active is None:
            resumable_turn_id = _resumable_turn_id(values)
        return ConversationResponse(
            conversation_id=conversation_id,
            messages=messages,
            active_turn_id=active.turn_id if active is not None else None,
            resumable_turn_id=resumable_turn_id,
        )

    async def _validate_new_turn(self, conversation_id: str, turn_id: str) -> None:
        if await self._registry.get(conversation_id) is not None:
            from app.core.errors import ConversationBusyError

            raise ConversationBusyError()
        values = await self._state_values(conversation_id)
        messages = values.get("messages", [])
        if _message_by_id(messages, f"{turn_id}:assistant") is not None:
            raise TurnAlreadyCompletedError()
        if _message_by_id(messages, f"{turn_id}:user") is not None:
            raise TurnRequiresResumeError()
        if _resumable_turn_id(values) is not None:
            raise TurnRequiresResumeError()

    async def _validate_resume(self, conversation_id: str, turn_id: str) -> None:
        if await self._registry.get(conversation_id) is not None:
            from app.core.errors import ConversationBusyError

            raise ConversationBusyError()
        values = await self._state_values(conversation_id)
        if not values:
            raise ConversationNotFoundError()
        if _message_by_id(values.get("messages", []), f"{turn_id}:assistant") is not None:
            raise TurnAlreadyCompletedError()
        if _resumable_turn_id(values) != turn_id:
            raise TurnRequiresResumeError()

    async def _is_resumable(self, conversation_id: str, turn_id: str) -> bool:
        values = await self._state_values(conversation_id)
        return _resumable_turn_id(values) == turn_id

    async def _final_message(
        self,
        conversation_id: str,
        turn_id: str,
    ) -> AIMessage | None:
        message = _message_by_id(
            (await self._state_values(conversation_id)).get("messages", []),
            f"{turn_id}:assistant",
        )
        return message if isinstance(message, AIMessage) else None

    async def _state_values(self, conversation_id: str) -> dict[str, Any]:
        snapshot = await self._graph.aget_state(conversation_config(conversation_id))
        return dict(snapshot.values) if snapshot.values else {}

    async def _graph_events(
        self,
        graph_input: dict[str, Any] | None,
        config: dict[str, Any],
        request: Request,
    ) -> AsyncIterator[object]:
        events: asyncio.Queue[object] = asyncio.Queue()
        completed = object()

        async def execute_graph() -> None:
            try:
                async for event in self._graph.astream(
                    graph_input,
                    config=config,
                    stream_mode="custom",
                ):
                    await events.put(event)
            except BaseException as error:
                await events.put(error)
            finally:
                await events.put(completed)

        graph_task = asyncio.create_task(execute_graph())
        try:
            while True:
                if await request.is_disconnected():
                    return
                try:
                    event = await asyncio.wait_for(events.get(), timeout=0.2)
                except TimeoutError:
                    continue
                if event is completed:
                    return
                if isinstance(event, BaseException):
                    raise event
                yield event
        finally:
            if not graph_task.done():
                graph_task.cancel()
                with suppress(asyncio.CancelledError):
                    await graph_task


def get_chat_runtime(request: Request) -> ChatRuntime:
    runtime = getattr(request.app.state, "chat_runtime", None)
    if runtime is None:
        raise ServiceUnavailableError("Chat")
    return runtime


@router.post("/chat/stream")
async def chat_stream(
    payload: ChatStreamRequest,
    request: Request,
    runtime: ChatRuntime = Depends(get_chat_runtime),
) -> StreamingResponse:
    conversation_id = str(payload.conversation_id)
    turn_id = str(payload.turn_id)
    run = await runtime.begin_new_turn(conversation_id, turn_id)
    thinking_enabled = (
        get_settings().chat_thinking_enabled
        if payload.thinking_enabled is None
        else payload.thinking_enabled
    )
    return StreamingResponse(
        runtime.stream(
            request,
            run,
            payload.message,
            resumed=False,
            thinking_enabled=thinking_enabled,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def conversation_history(
    conversation_id: UUID,
    runtime: ChatRuntime = Depends(get_chat_runtime),
) -> ConversationResponse:
    return await runtime.history(str(conversation_id))


@router.post("/conversations/{conversation_id}/turns/{turn_id}/resume/stream")
async def resume_chat_stream(
    conversation_id: UUID,
    turn_id: UUID,
    request: Request,
    runtime: ChatRuntime = Depends(get_chat_runtime),
) -> StreamingResponse:
    run = await runtime.begin_resume(str(conversation_id), str(turn_id))
    return StreamingResponse(
        runtime.stream(request, run, message=None, resumed=True),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _graph_event(value: object) -> tuple[str, dict[str, object]] | None:
    if not isinstance(value, dict):
        return None
    event = value.get("event")
    data = value.get("data")
    if not isinstance(event, str) or not isinstance(data, dict):
        return None
    return event, data


def _public_messages(messages: list[BaseMessage]) -> list[ConversationMessage]:
    projected: list[ConversationMessage] = []
    for message in messages:
        if isinstance(message, HumanMessage):
            projected.append(
                ConversationMessage(
                    id=message.id or "",
                    turn_id=_turn_id(message.id),
                    role="user",
                    content=_message_content(message),
                )
            )
        elif isinstance(message, AIMessage) and "answer_status" in message.additional_kwargs:
            projected.append(
                ConversationMessage(
                    id=message.id or "",
                    turn_id=str(message.additional_kwargs.get("turn_id") or _turn_id(message.id)),
                    role="assistant",
                    content=_message_content(message),
                    answer_status=message.additional_kwargs.get("answer_status"),
                    sources=_message_sources(message),
                )
            )
    return projected


def _message_sources(message: AIMessage) -> list[Source]:
    raw_sources = message.additional_kwargs.get("sources", [])
    if not isinstance(raw_sources, list):
        return []
    sources: list[Source] = []
    for source in raw_sources:
        try:
            sources.append(Source.model_validate(source))
        except Exception:
            continue
    return sources


def _message_by_id(messages: list[BaseMessage], message_id: str) -> BaseMessage | None:
    return next((message for message in messages if message.id == message_id), None)


def _resumable_turn_id(values: dict[str, Any]) -> str | None:
    turn_id = values.get("turn_id")
    if not isinstance(turn_id, str):
        return None
    messages = values.get("messages", [])
    if _message_by_id(messages, f"{turn_id}:user") is None:
        return None
    return None if _message_by_id(messages, f"{turn_id}:assistant") is not None else turn_id


def _turn_id(message_id: str | None) -> str:
    return message_id.rsplit(":", 1)[0] if message_id else ""


def _message_content(message: BaseMessage) -> str:
    return message.text if isinstance(message.content, str) else str(message.content)


def _answer_chunks(answer: str) -> list[str]:
    return [answer[index : index + 80] for index in range(0, len(answer), 80)] or [""]


def _stream_error(error: Exception) -> tuple[str, str]:
    if isinstance(error, ServiceUnavailableError):
        return error.code, error.message
    return "GRAPH_EXECUTION_ERROR", "系统执行异常"
