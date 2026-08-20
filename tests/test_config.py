from app.core.config import Settings


def test_reranker_is_disabled_when_all_values_are_empty() -> None:
    settings = Settings(
        _env_file=None,
        postgres_uri="postgresql://user:password@localhost:5432/ace_rag",
        redis_url="redis://localhost:6379/0",
        milvus_uri="http://localhost:19530",
        chat_model_provider="deepseek",
        chat_model_base_url="https://api.deepseek.com",
        chat_model_name="deepseek-v4-flash",
        embedding_model_provider="siliconflow",
        embedding_model_base_url="https://api.siliconflow.cn/v1",
        embedding_model_name="BAAI/bge-m3",
        reranker_model_provider="",
        reranker_model_base_url="",
        reranker_model_name="",
        reranker_model_api_key="",
    )

    assert settings.uvicorn_workers == 1
    assert settings.reranker_model_provider is None
    assert settings.reranker_model_name is None
