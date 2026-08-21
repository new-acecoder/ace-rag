from __future__ import annotations

import hashlib
import json

import redis.asyncio as redis

from app.core.config import Settings
from app.core.errors import ServiceUnavailableError
from app.rag.schemas import RetrievedChunk


class RetrievalCache:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def increment_index_version(self) -> None:
        client = redis.from_url(self._settings.redis_url)
        try:
            await client.incr(self._settings.rag_index_version_key)
        except Exception as error:
            raise ServiceUnavailableError("Redis") from error
        finally:
            await client.aclose()

    async def get(self, query: str, top_k: int) -> list[RetrievedChunk] | None:
        client = redis.from_url(self._settings.redis_url)
        try:
            index_version = await self._index_version(client)
            value = await client.get(self._key(index_version, query, top_k))
        except Exception as error:
            raise ServiceUnavailableError("Redis") from error
        finally:
            await client.aclose()

        if value is None:
            return None
        try:
            payload = json.loads(value)
            return [RetrievedChunk.model_validate(item) for item in payload]
        except (TypeError, ValueError, json.JSONDecodeError):
            return None

    async def set(self, query: str, top_k: int, chunks: list[RetrievedChunk]) -> None:
        client = redis.from_url(self._settings.redis_url)
        try:
            index_version = await self._index_version(client)
            payload = json.dumps([chunk.model_dump(mode="json") for chunk in chunks])
            await client.setex(
                self._key(index_version, query, top_k),
                self._settings.rag_cache_ttl,
                payload,
            )
        except Exception as error:
            raise ServiceUnavailableError("Redis") from error
        finally:
            await client.aclose()

    async def _index_version(self, client: redis.Redis) -> str:
        value = await client.get(self._settings.rag_index_version_key)
        if value is None:
            return "0"
        if isinstance(value, bytes):
            return value.decode()
        return str(value)

    @staticmethod
    def _key(index_version: str, query: str, top_k: int) -> str:
        payload = json.dumps(
            {"query": query, "top_k": top_k, "filters": {}},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(payload.encode()).hexdigest()
        return f"rag:retrieval:{index_version}:{digest}"
