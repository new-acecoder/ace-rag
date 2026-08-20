from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

import asyncpg

from app.core.config import Settings
from app.core.errors import (
    IngestionJobNotCancellableError,
    IngestionJobNotFoundError,
    ServiceUnavailableError,
)
from app.rag.schemas import IngestionJob, IngestionStage, IngestionStatus


@dataclass(frozen=True, slots=True)
class IngestionJobRecord:
    job: IngestionJob
    object_key: str
    collection_name: str
    embedding_model_name: str
    attempt_count: int
    available_at: datetime


@dataclass(frozen=True, slots=True)
class OutboxEvent:
    event_id: str
    job_id: str
    event_type: str
    payload: dict[str, str]


class IngestionJobRepository:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def create(
        self,
        document_id: str,
        source: str,
        document_type: str,
        object_key: str,
    ) -> IngestionJob:
        job_id = str(uuid4())
        event_id = str(uuid4())
        connection = await self._connect()
        try:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    INSERT INTO ingestion_jobs(
                        job_id, document_id, source, document_type, object_key, status,
                        collection_name, embedding_model_name
                    )
                    VALUES ($1::uuid, $2::uuid, $3, $4, $5, 'queued', $6, $7)
                    RETURNING *
                    """,
                    job_id,
                    document_id,
                    source,
                    document_type,
                    object_key,
                    self._settings.milvus_collection_name,
                    self._settings.embedding_model_name,
                )
                await self._insert_outbox_event(connection, event_id, job_id)
        finally:
            await connection.close()
        return self._to_record(row).job

    async def get(self, job_id: str) -> IngestionJobRecord:
        connection = await self._connect()
        try:
            row = await connection.fetchrow(
                "SELECT * FROM ingestion_jobs WHERE job_id = $1::uuid", job_id
            )
        finally:
            await connection.close()
        if row is None:
            raise IngestionJobNotFoundError()
        return self._to_record(row)

    async def list_visible(self) -> list[IngestionJob]:
        connection = await self._connect()
        try:
            rows = await connection.fetch(
                """
                SELECT * FROM ingestion_jobs
                WHERE status IN ('queued', 'processing', 'cancel_requested')
                   OR (
                       status = 'failed'
                       AND updated_at >= NOW() - ($1::int * INTERVAL '1 day')
                   )
                ORDER BY created_at DESC
                """,
                self._settings.ingestion_job_retention_days,
            )
        finally:
            await connection.close()
        return [self._to_record(row).job for row in rows]

    async def request_cancel(self, job_id: str) -> IngestionJob:
        connection = await self._connect()
        try:
            async with connection.transaction():
                row = await connection.fetchrow(
                    "SELECT * FROM ingestion_jobs WHERE job_id = $1::uuid FOR UPDATE", job_id
                )
                if row is None:
                    raise IngestionJobNotFoundError()
                if row["status"] == "cancel_requested":
                    return self._to_record(row).job
                if row["status"] not in {"queued", "processing"}:
                    raise IngestionJobNotCancellableError()
                row = await connection.fetchrow(
                    """
                    UPDATE ingestion_jobs
                    SET status = 'cancel_requested', updated_at = NOW()
                    WHERE job_id = $1::uuid
                    RETURNING *
                    """,
                    job_id,
                )
        finally:
            await connection.close()
        return self._to_record(row).job

    async def claim(self, job_id: str) -> IngestionJobRecord | None:
        connection = await self._connect()
        try:
            async with connection.transaction():
                row = await connection.fetchrow(
                    "SELECT * FROM ingestion_jobs WHERE job_id = $1::uuid FOR UPDATE", job_id
                )
                if row is None or row["status"] != "queued" or row["available_at"] > datetime.now(UTC):
                    return None
                row = await connection.fetchrow(
                    """
                    UPDATE ingestion_jobs
                    SET status = 'processing', stage = 'parsing', attempt_count = attempt_count + 1,
                        error_code = NULL, error_message = NULL, updated_at = NOW()
                    WHERE job_id = $1::uuid
                    RETURNING *
                    """,
                    job_id,
                )
        finally:
            await connection.close()
        return self._to_record(row)

    async def is_cancel_requested(self, job_id: str) -> bool:
        connection = await self._connect()
        try:
            return bool(
                await connection.fetchval(
                    """
                    SELECT status = 'cancel_requested'
                    FROM ingestion_jobs
                    WHERE job_id = $1::uuid
                    """,
                    job_id,
                )
            )
        finally:
            await connection.close()

    async def set_stage(self, job_id: str, stage: IngestionStage) -> None:
        connection = await self._connect()
        try:
            await connection.execute(
                """
                UPDATE ingestion_jobs
                SET stage = $2, updated_at = NOW()
                WHERE job_id = $1::uuid AND status = 'processing'
                """,
                job_id,
                stage,
            )
        finally:
            await connection.close()

    async def mark_ready(self, job_id: str, chunk_count: int) -> bool:
        connection = await self._connect()
        try:
            row = await connection.fetchrow(
                """
                UPDATE ingestion_jobs
                SET status = 'ready', stage = NULL, chunk_count = $2,
                    updated_at = NOW(), finished_at = NOW()
                WHERE job_id = $1::uuid AND status = 'processing'
                RETURNING job_id
                """,
                job_id,
                chunk_count,
            )
        finally:
            await connection.close()
        return row is not None

    async def mark_cancelled(self, job_id: str) -> None:
        connection = await self._connect()
        try:
            await connection.execute(
                """
                UPDATE ingestion_jobs
                SET status = 'cancelled', stage = NULL, updated_at = NOW(), finished_at = NOW()
                WHERE job_id = $1::uuid
                """,
                job_id,
            )
        finally:
            await connection.close()

    async def mark_failed(self, job_id: str, code: str, message: str) -> None:
        connection = await self._connect()
        try:
            await connection.execute(
                """
                UPDATE ingestion_jobs
                SET status = 'failed', stage = NULL, error_code = $2, error_message = $3,
                    updated_at = NOW(), finished_at = NOW()
                WHERE job_id = $1::uuid
                """,
                job_id,
                code,
                message,
            )
        finally:
            await connection.close()

    async def retry(self, job_id: str, code: str, message: str, delay_seconds: int) -> None:
        connection = await self._connect()
        try:
            async with connection.transaction():
                await connection.execute(
                    """
                    UPDATE ingestion_jobs
                    SET status = 'queued', stage = NULL,
                        available_at = NOW() + ($2 * INTERVAL '1 second'),
                        error_code = $3, error_message = $4, updated_at = NOW()
                    WHERE job_id = $1::uuid
                    """,
                    job_id,
                    delay_seconds,
                    code,
                    message,
                )
                await self._insert_outbox_event(
                    connection,
                    str(uuid4()),
                    job_id,
                    delay_seconds,
                )
        finally:
            await connection.close()

    async def find_by_document_id(self, document_id: str) -> IngestionJobRecord | None:
        connection = await self._connect()
        try:
            row = await connection.fetchrow(
                "SELECT * FROM ingestion_jobs WHERE document_id = $1::uuid", document_id
            )
        finally:
            await connection.close()
        return self._to_record(row) if row else None

    async def delete_by_document_id(self, document_id: str) -> None:
        connection = await self._connect()
        try:
            await connection.execute("DELETE FROM ingestion_jobs WHERE document_id = $1::uuid", document_id)
        finally:
            await connection.close()

    async def _connect(self) -> asyncpg.Connection:
        try:
            return await asyncpg.connect(self._settings.postgres_uri, timeout=5)
        except Exception as error:
            raise ServiceUnavailableError("PostgreSQL") from error

    async def _insert_outbox_event(
        self,
        connection: asyncpg.Connection,
        event_id: str,
        job_id: str,
        delay_seconds: int = 0,
    ) -> None:
        await connection.execute(
            """
            INSERT INTO outbox_events(event_id, job_id, event_type, payload, available_at)
            VALUES (
                $1::uuid,
                $2::uuid,
                'ingestion.requested',
                $3::jsonb,
                NOW() + ($4 * INTERVAL '1 second')
            )
            """,
            event_id,
            job_id,
            json.dumps({"job_id": job_id}),
            delay_seconds,
        )

    @staticmethod
    def _to_record(row: asyncpg.Record) -> IngestionJobRecord:
        data = dict(row)
        job_data = {
            key: data[key]
            for key in (
                "job_id",
                "document_id",
                "source",
                "document_type",
                "status",
                "stage",
                "chunk_count",
                "error_code",
                "error_message",
                "created_at",
                "updated_at",
            )
        }
        job_data["job_id"] = str(job_data["job_id"])
        job_data["document_id"] = str(job_data["document_id"])
        job = IngestionJob.model_validate(
            job_data
        )
        return IngestionJobRecord(
            job=job,
            object_key=data["object_key"],
            collection_name=data["collection_name"],
            embedding_model_name=data["embedding_model_name"],
            attempt_count=data["attempt_count"],
            available_at=data["available_at"],
        )


class OutboxRepository:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def claim(self, limit: int = 20) -> list[OutboxEvent]:
        connection = await asyncpg.connect(self._settings.postgres_uri)
        try:
            rows = await connection.fetch(
                """
                WITH candidates AS (
                    SELECT event_id
                    FROM outbox_events
                    WHERE published_at IS NULL
                      AND available_at <= NOW()
                      AND (locked_until IS NULL OR locked_until < NOW())
                    ORDER BY created_at
                    FOR UPDATE SKIP LOCKED
                    LIMIT $1
                )
                UPDATE outbox_events event
                SET locked_until = NOW() + INTERVAL '30 seconds'
                FROM candidates
                WHERE event.event_id = candidates.event_id
                RETURNING event.event_id, event.job_id, event.event_type, event.payload
                """,
                limit,
            )
        finally:
            await connection.close()
        return [
            OutboxEvent(
                event_id=str(row["event_id"]),
                job_id=str(row["job_id"]),
                event_type=row["event_type"],
                payload=self._payload_as_dict(row["payload"]),
            )
            for row in rows
        ]

    async def mark_published(self, event_id: str) -> None:
        await self._set_lock(event_id, published=True)

    async def release(self, event_id: str) -> None:
        await self._set_lock(event_id, published=False)

    async def _set_lock(self, event_id: str, published: bool) -> None:
        connection = await asyncpg.connect(self._settings.postgres_uri)
        try:
            if published:
                await connection.execute(
                    """
                    UPDATE outbox_events
                    SET published_at = NOW(), locked_until = NULL
                    WHERE event_id = $1::uuid
                    """,
                    event_id,
                )
            else:
                await connection.execute(
                    "UPDATE outbox_events SET locked_until = NULL WHERE event_id = $1::uuid",
                    event_id,
                )
        finally:
            await connection.close()

    @staticmethod
    def _payload_as_dict(payload: object) -> dict[str, str]:
        if isinstance(payload, str):
            return json.loads(payload)
        return dict(payload)
