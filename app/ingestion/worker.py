from __future__ import annotations

import asyncio
import json
from contextlib import suppress

import aio_pika

from app.cache.retrieval_cache import RetrievalCache
from app.core.config import Settings, get_settings
from app.core.errors import ApiException, IngestionCancelledError, ServiceUnavailableError
from app.db.migrator import run_migrations
from app.ingestion.jobs import IngestionJobRecord, IngestionJobRepository, OutboxRepository
from app.ingestion.kernel import IngestionKernel
from app.ingestion.outbox import OutboxPublisher
from app.mq.rabbitmq import RabbitMQBroker
from app.rag.embedding import EmbeddingService
from app.rag.milvus import MilvusChunkRepository
from app.storage.document_objects import DocumentObjectStore


class IngestionWorker:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._jobs = IngestionJobRepository(settings)
        self._broker = RabbitMQBroker(settings)
        self._kernel = IngestionKernel(
            settings=settings,
            object_store=DocumentObjectStore(settings),
            jobs=self._jobs,
            embedding_service=EmbeddingService(settings),
            repository=MilvusChunkRepository(settings),
            retrieval_cache=RetrievalCache(settings),
        )

    async def run(self) -> None:
        connection = await self._broker.connect()
        try:
            channel = await connection.channel()
            await channel.set_qos(prefetch_count=self._settings.ingestion_worker_concurrency)
            await self._broker.declare_topology(channel)
            queue = await channel.get_queue(self._settings.rabbitmq_ingestion_queue)
            async with queue.iterator() as messages:
                async for message in messages:
                    await self._handle_message(message)
        finally:
            await connection.close()

    async def _handle_message(self, message: aio_pika.abc.AbstractIncomingMessage) -> None:
        try:
            job_id = json.loads(message.body).get("job_id")
            if not isinstance(job_id, str):
                raise ValueError("missing job_id")
        except Exception:
            await message.reject(requeue=False)
            return

        try:
            record = await self._jobs.claim(job_id)
        except ServiceUnavailableError:
            await message.reject(requeue=True)
            return
        if record is None:
            await self._cancel_if_requested(job_id)
            await message.ack()
            return

        try:
            chunk_count = await self._kernel.ingest(record)
        except IngestionCancelledError:
            await self._cancel(record)
            await message.ack()
        except ServiceUnavailableError as error:
            await self._retry_or_fail(record, error)
            await message.ack()
        except ApiException as error:
            await self._fail(record, error.code, error.message)
            await message.reject(requeue=False)
        except Exception:
            await self._fail(record, "DOCUMENT_INGESTION_FAILED", "文档入库失败")
            await message.reject(requeue=False)
        else:
            if await self._jobs.mark_ready(record.job.job_id, chunk_count):
                await message.ack()
            else:
                await self._cancel(record)
                await message.ack()

    async def _cancel_if_requested(self, job_id: str) -> None:
        with suppress(ApiException):
            record = await self._jobs.get(job_id)
            if record.job.status == "cancel_requested":
                await self._cancel(record)

    async def _cancel(self, record: IngestionJobRecord) -> None:
        await self._kernel.cancel(record)
        await self._jobs.mark_cancelled(record.job.job_id)

    async def _retry_or_fail(self, record: IngestionJobRecord, error: ServiceUnavailableError) -> None:
        await self._kernel.cleanup_chunks(record)
        if record.attempt_count >= self._settings.ingestion_max_attempts:
            await self._jobs.mark_failed(record.job.job_id, error.code, error.message)
            return
        delay = self._settings.ingestion_retry_base_seconds * (2 ** (record.attempt_count - 1))
        await self._jobs.retry(record.job.job_id, error.code, error.message, delay)

    async def _fail(self, record: IngestionJobRecord, code: str, message: str) -> None:
        await self._kernel.cleanup_chunks(record)
        await self._jobs.mark_failed(record.job.job_id, code, message)


async def run_worker() -> None:
    settings = get_settings()
    await run_migrations(settings)
    await DocumentObjectStore(settings).check_health()
    publisher = OutboxPublisher(OutboxRepository(settings), RabbitMQBroker(settings))
    stop_event = asyncio.Event()
    publisher_task = asyncio.create_task(publisher.run_forever(stop_event))
    try:
        worker = IngestionWorker(settings)
        while True:
            try:
                await worker.run()
            except ServiceUnavailableError:
                await asyncio.sleep(1)
    finally:
        stop_event.set()
        publisher_task.cancel()
        with suppress(asyncio.CancelledError):
            await publisher_task


if __name__ == "__main__":
    asyncio.run(run_worker())
