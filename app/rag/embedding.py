from __future__ import annotations

import asyncio

from langchain_openai import OpenAIEmbeddings

from app.core.config import Settings
from app.core.errors import ServiceUnavailableError


class EmbeddingService:
    def __init__(self, settings: Settings) -> None:
        api_key = settings.embedding_model_api_key
        if api_key is None:
            raise ServiceUnavailableError("Embedding 模型")

        self._client = OpenAIEmbeddings(
            model=settings.embedding_model_name,
            api_key=api_key.get_secret_value(),
            base_url=settings.embedding_model_base_url,
            check_embedding_ctx_length=False,
        )

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        try:
            embeddings = await asyncio.to_thread(self._client.embed_documents, texts)
        except Exception as error:
            raise ServiceUnavailableError("Embedding 模型") from error

        if not embeddings or len(embeddings) != len(texts):
            raise ServiceUnavailableError("Embedding 模型")
        return embeddings
