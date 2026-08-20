from __future__ import annotations

import redis.asyncio as redis

from app.core.config import Settings
from app.core.errors import ServiceUnavailableError


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
