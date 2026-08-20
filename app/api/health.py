from __future__ import annotations

import asyncio
from typing import Literal

import asyncpg
import redis.asyncio as redis
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from pymilvus import MilvusClient

from app.core.config import Settings, get_settings
from app.core.errors import ServiceUnavailableError
from app.mq.rabbitmq import RabbitMQBroker
from app.storage.document_objects import DocumentObjectStore

router = APIRouter(prefix="/api/v1", tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str | None = None


async def check_postgres(settings: Settings) -> None:
    try:
        connection = await asyncpg.connect(settings.postgres_uri, timeout=3)
        try:
            await connection.execute("SELECT 1")
        finally:
            await connection.close()
    except Exception as error:
        raise ServiceUnavailableError("PostgreSQL") from error


async def check_redis(settings: Settings) -> None:
    client = redis.from_url(settings.redis_url)
    try:
        await client.ping()
    except Exception as error:
        raise ServiceUnavailableError("Redis") from error
    finally:
        await client.aclose()


def _list_milvus_collections(uri: str) -> None:
    MilvusClient(uri=uri).list_collections()


async def check_milvus(settings: Settings) -> None:
    try:
        await asyncio.to_thread(_list_milvus_collections, settings.milvus_uri)
    except Exception as error:
        raise ServiceUnavailableError("Milvus") from error


async def check_minio(settings: Settings) -> None:
    await DocumentObjectStore(settings).check_health()


async def check_rabbitmq(settings: Settings) -> None:
    await RabbitMQBroker(settings).check_health()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


@router.get("/health/postgres", response_model=HealthResponse)
async def postgres_health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    await check_postgres(settings)
    return HealthResponse(service="postgres")


@router.get("/health/redis", response_model=HealthResponse)
async def redis_health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    await check_redis(settings)
    return HealthResponse(service="redis")


@router.get("/health/milvus", response_model=HealthResponse)
async def milvus_health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    await check_milvus(settings)
    return HealthResponse(service="milvus")


@router.get("/health/minio", response_model=HealthResponse)
async def minio_health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    await check_minio(settings)
    return HealthResponse(service="minio")


@router.get("/health/rabbitmq", response_model=HealthResponse)
async def rabbitmq_health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    await check_rabbitmq(settings)
    return HealthResponse(service="rabbitmq")
