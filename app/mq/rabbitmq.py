from __future__ import annotations

import json

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message

from app.core.config import Settings
from app.core.errors import ServiceUnavailableError


class RabbitMQBroker:
    routing_key = "ingestion.requested"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def connect(self) -> aio_pika.abc.AbstractRobustConnection:
        try:
            return await aio_pika.connect_robust(
                self._settings.rabbitmq_url.get_secret_value(),
                timeout=5,
            )
        except Exception as error:
            raise ServiceUnavailableError("RabbitMQ") from error

    async def declare_topology(self, channel: aio_pika.abc.AbstractChannel) -> None:
        exchange = await channel.declare_exchange(
            self._settings.rabbitmq_ingestion_queue,
            ExchangeType.DIRECT,
            durable=True,
        )
        dead_letter_exchange = await channel.declare_exchange(
            self._settings.rabbitmq_ingestion_dlx,
            ExchangeType.DIRECT,
            durable=True,
        )
        queue = await channel.declare_queue(
            self._settings.rabbitmq_ingestion_queue,
            durable=True,
            arguments={
                "x-dead-letter-exchange": dead_letter_exchange.name,
                "x-dead-letter-routing-key": self.routing_key,
            },
        )
        dead_letter_queue = await channel.declare_queue(
            f"{self._settings.rabbitmq_ingestion_queue}.dlq",
            durable=True,
        )
        await queue.bind(exchange, routing_key=self.routing_key)
        await dead_letter_queue.bind(dead_letter_exchange, routing_key=self.routing_key)

    async def publish(
        self,
        channel: aio_pika.abc.AbstractChannel,
        event_id: str,
        job_id: str,
    ) -> None:
        exchange = await channel.get_exchange(self._settings.rabbitmq_ingestion_queue)
        await exchange.publish(
            Message(
                body=json.dumps({"job_id": job_id}).encode(),
                content_type="application/json",
                delivery_mode=DeliveryMode.PERSISTENT,
                message_id=event_id,
            ),
            routing_key=self.routing_key,
        )

    async def check_health(self) -> None:
        connection = await self.connect()
        await connection.close()
