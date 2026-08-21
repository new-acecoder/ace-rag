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
    rag_dense_top_k: int = 10
    rag_bm25_top_k: int = 10
    rag_final_top_k: int = 5
    rag_cache_ttl: int = 300
    rag_index_version_key: str = "rag:retrieval:index_version"

    max_plan_steps: int = 5
    max_replan_count: int = 2
    max_reflection_count: int = 1
    max_retrieval_count: int = 6
    max_agentic_retrieval_rounds: int = 3
    max_retrieval_queries_per_round: int = 4
    react_max_tool_calls: int = 5
    react_max_model_calls: int = 6
    context_max_input_tokens: int = 12_000
    context_reserved_output_tokens: int = 2_048

    langsmith_tracing: bool = True
    langsmith_project: str = "ace-rag"
    langsmith_api_key: SecretStr | None = None

    chat_model_provider: str
    chat_model_base_url: str
    chat_model_name: str
    chat_model_api_key: SecretStr | None = None
    chat_thinking_enabled: bool = True

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
        if self.rag_dense_top_k <= 0:
            raise ValueError("RAG_DENSE_TOP_K must be positive")
        if self.rag_bm25_top_k <= 0:
            raise ValueError("RAG_BM25_TOP_K must be positive")
        if self.rag_final_top_k <= 0:
            raise ValueError("RAG_FINAL_TOP_K must be positive")
        if self.rag_cache_ttl <= 0:
            raise ValueError("RAG_CACHE_TTL must be positive")
        if self.max_plan_steps <= 0:
            raise ValueError("MAX_PLAN_STEPS must be positive")
        if self.max_replan_count < 0:
            raise ValueError("MAX_REPLAN_COUNT must not be negative")
        if self.max_reflection_count < 0:
            raise ValueError("MAX_REFLECTION_COUNT must not be negative")
        if self.max_retrieval_count <= 0:
            raise ValueError("MAX_RETRIEVAL_COUNT must be positive")
        if self.max_agentic_retrieval_rounds <= 0:
            raise ValueError("MAX_AGENTIC_RETRIEVAL_ROUNDS must be positive")
        if self.max_retrieval_queries_per_round <= 0:
            raise ValueError("MAX_RETRIEVAL_QUERIES_PER_ROUND must be positive")
        if self.react_max_tool_calls <= 0:
            raise ValueError("REACT_MAX_TOOL_CALLS must be positive")
        if self.react_max_model_calls <= 0:
            raise ValueError("REACT_MAX_MODEL_CALLS must be positive")
        if self.context_max_input_tokens <= 0:
            raise ValueError("CONTEXT_MAX_INPUT_TOKENS must be positive")
        if self.context_reserved_output_tokens < 0:
            raise ValueError("CONTEXT_RESERVED_OUTPUT_TOKENS must not be negative")
        if self.context_reserved_output_tokens >= self.context_max_input_tokens:
            raise ValueError(
                "CONTEXT_RESERVED_OUTPUT_TOKENS must be smaller than CONTEXT_MAX_INPUT_TOKENS"
            )

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
