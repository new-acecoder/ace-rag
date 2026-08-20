from datetime import UTC, datetime
from uuid import UUID

from app.ingestion.jobs import IngestionJobRepository, OutboxRepository


def test_job_record_converts_postgres_uuid_values_to_dto_strings() -> None:
    job_id = UUID("6284e739-1b95-4269-b529-49f61e9ed2e0")
    document_id = UUID("e1a15f29-8b69-4f94-881e-0f4043965afe")
    now = datetime(2026, 8, 20, tzinfo=UTC)

    record = IngestionJobRepository._to_record(
        {
            "job_id": job_id,
            "document_id": document_id,
            "source": "travel-policy.txt",
            "document_type": "txt",
            "object_key": "documents/example/original.txt",
            "status": "queued",
            "stage": None,
            "chunk_count": None,
            "collection_name": "ace_rag_chunks",
            "embedding_model_name": "BAAI/bge-m3",
            "attempt_count": 0,
            "available_at": now,
            "error_code": None,
            "error_message": None,
            "created_at": now,
            "updated_at": now,
        }
    )

    assert record.job.job_id == str(job_id)
    assert record.job.document_id == str(document_id)


def test_outbox_payload_accepts_asyncpg_jsonb_text() -> None:
    assert OutboxRepository._payload_as_dict('{"job_id": "job-1"}') == {"job_id": "job-1"}
