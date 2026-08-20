from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    uvicorn_workers: int = 1

    postgres_uri: str
    redis_url: str
    milvus_uri: str
    milvus_collection_name: str = "ace_rag_chunks"

    minio_endpoint: str = "127.0.0.1:9000"
    minio_access_key: SecretStr = SecretStr("minioadmin")
    minio_secret_key: SecretStr = SecretStr("minioadmin")
    minio_secure: bool = False
    minio_upload_bucket: str = "ace-rag-uploads"

    rabbitmq_url: SecretStr = SecretStr("amqp://ace_rag:ace_rag_dev@127.0.0.1:5672/")
    rabbitmq_ingestion_queue: str = "ace-rag.ingestion"
    rabbitmq_ingestion_dlx: str = "ace-rag.ingestion.dlx"

    ingestion_worker_concurrency: int = 1
    ingestion_max_attempts: int = 3
    ingestion_retry_base_seconds: int = 10
    ingestion_job_retention_days: int = 7

    document_max_upload_bytes: int = 10 * 1024 * 1024
    rag_chunk_size_chars: int = 800
    rag_chunk_overlap_chars: int = 120
    rag_index_version_key: str = "rag:retrieval:index_version"

    langsmith_tracing: bool = True
    langsmith_project: str = "ace-rag"
    langsmith_api_key: SecretStr | None = None

    chat_model_provider: str
    chat_model_base_url: str
    chat_model_name: str
    chat_model_api_key: SecretStr | None = None

    embedding_model_provider: str
    embedding_model_base_url: str
    embedding_model_name: str
    embedding_model_api_key: SecretStr | None = None

    reranker_model_provider: str | None = None
    reranker_model_base_url: str | None = None
    reranker_model_name: str | None = None
    reranker_model_api_key: SecretStr | None = None

    @field_validator(
        "langsmith_api_key",
        "chat_model_api_key",
        "embedding_model_api_key",
        "minio_access_key",
        "minio_secret_key",
        "rabbitmq_url",
        "reranker_model_api_key",
        "reranker_model_provider",
        "reranker_model_base_url",
        "reranker_model_name",
        mode="before",
    )
    @classmethod
    def empty_values_are_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def validate_single_worker_and_reranker(self) -> Settings:
        if self.uvicorn_workers != 1:
            raise ValueError("UVICORN_WORKERS must be 1 for V1")
        if self.document_max_upload_bytes <= 0:
            raise ValueError("DOCUMENT_MAX_UPLOAD_BYTES must be positive")
        if self.ingestion_worker_concurrency <= 0:
            raise ValueError("INGESTION_WORKER_CONCURRENCY must be positive")
        if self.ingestion_max_attempts <= 0:
            raise ValueError("INGESTION_MAX_ATTEMPTS must be positive")
        if self.ingestion_retry_base_seconds <= 0:
            raise ValueError("INGESTION_RETRY_BASE_SECONDS must be positive")
        if self.ingestion_job_retention_days <= 0:
            raise ValueError("INGESTION_JOB_RETENTION_DAYS must be positive")
        if self.rag_chunk_size_chars <= 0:
            raise ValueError("RAG_CHUNK_SIZE_CHARS must be positive")
        if not 0 <= self.rag_chunk_overlap_chars < self.rag_chunk_size_chars:
            raise ValueError("RAG_CHUNK_OVERLAP_CHARS must be smaller than chunk size")

        reranker_values = (
            self.reranker_model_provider,
            self.reranker_model_base_url,
            self.reranker_model_name,
            self.reranker_model_api_key,
        )
        if any(reranker_values) and not all(reranker_values):
            raise ValueError("Reranker configuration must be complete or disabled")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
