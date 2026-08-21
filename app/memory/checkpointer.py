from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from app.core.config import Settings


@asynccontextmanager
async def postgres_checkpointer(settings: Settings) -> AsyncIterator[AsyncPostgresSaver]:
    async with AsyncPostgresSaver.from_conn_string(
        settings.postgres_uri,
        serde=create_checkpoint_serializer(),
    ) as checkpointer:
        await checkpointer.setup()
        yield checkpointer


def create_checkpoint_serializer() -> JsonPlusSerializer:
    return JsonPlusSerializer(
        allowed_msgpack_modules=[
            ("app.graph.state", "PlanStep"),
            ("app.graph.state", "StepResult"),
            ("app.graph.state", "RetrievalGrade"),
            ("app.graph.state", "AnswerEvaluation"),
            ("app.graph.state", "ReflectionDecision"),
            ("app.rag.agentic.schemas", "EvidenceGrade"),
            ("app.rag.agentic.schemas", "KnowledgeSearchResult"),
            ("app.rag.schemas", "RetrievedChunk"),
            ("app.rag.schemas", "Source"),
        ]
    )
