from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import uuid4

from app.core.errors import ConversationBusyError


@dataclass(frozen=True, slots=True)
class ActiveRun:
    conversation_id: str
    turn_id: str
    run_id: str


class ConversationRunRegistry:
    def __init__(self) -> None:
        self._active_runs: dict[str, ActiveRun] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, conversation_id: str, turn_id: str) -> ActiveRun:
        async with self._lock:
            if conversation_id in self._active_runs:
                raise ConversationBusyError()
            run = ActiveRun(
                conversation_id=conversation_id,
                turn_id=turn_id,
                run_id=str(uuid4()),
            )
            self._active_runs[conversation_id] = run
            return run

    async def get(self, conversation_id: str) -> ActiveRun | None:
        async with self._lock:
            return self._active_runs.get(conversation_id)

    async def release(self, run: ActiveRun) -> None:
        async with self._lock:
            if self._active_runs.get(run.conversation_id) == run:
                del self._active_runs[run.conversation_id]
