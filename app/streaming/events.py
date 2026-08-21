from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from langgraph.config import get_stream_writer
from langgraph.types import StreamWriter

_event_writer: ContextVar[StreamWriter | None] = ContextVar(
    "ace_rag_event_writer",
    default=None,
)


def emit_event(event: str, **data: Any) -> None:
    writer = _event_writer.get() or get_stream_writer()
    writer({"event": event, "data": data})


@contextmanager
def forward_stream_events() -> Iterator[None]:
    if _event_writer.get() is not None:
        yield
        return
    try:
        writer = get_stream_writer()
    except RuntimeError:
        yield
        return
    token = _event_writer.set(writer)
    try:
        yield
    finally:
        _event_writer.reset(token)
