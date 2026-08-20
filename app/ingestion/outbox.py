from __future__ import annotations

import asyncio

from app.ingestion.jobs import OutboxRepository
from app.mq.rabbitmq import RabbitMQBroker


class OutboxPublisher:
    def __init__(self, repository: OutboxRepository, broker: RabbitMQBroker) -> None:
        self._repository = repository
        self._broker = broker

    async def run_once(self) -> int:
        events = await self._repository.claim()
        if not events:
            return 0

        connection = await self._broker.connect()
        try:
            channel = await connection.channel(publisher_confirms=True)
            await self._broker.declare_topology(channel)
            published = 0
            for event in events:
                try:
                    await self._broker.publish(channel, event.event_id, event.job_id)
                except Exception:
                    await self._repository.release(event.event_id)
                    continue
                await self._repository.mark_published(event.event_id)
                published += 1
            return published
        finally:
            await connection.close()

    async def run_forever(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            try:
                published = await self.run_once()
            except Exception:
                published = 0
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=0.2 if published else 1)
            except TimeoutError:
                pass
