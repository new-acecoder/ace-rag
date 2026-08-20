from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.documents import (
    get_document_catalog_service,
    get_document_upload_service,
    get_ingestion_job_repository,
)
from app.core.errors import DocumentNotFoundError, IngestionJobNotCancellableError
from app.main import create_app
from app.rag.schemas import DocumentItem, IngestionJob


DOCUMENT_ID = "e1a15f29-8b69-4f94-881e-0f4043965afe"
JOB_ID = "6284e739-1b95-4269-b529-49f61e9ed2e0"
NOW = datetime(2026, 8, 20, tzinfo=UTC)


def ingestion_job(
    *,
    status: str = "queued",
    stage: str | None = None,
) -> IngestionJob:
    return IngestionJob(
        job_id=JOB_ID,
        document_id=DOCUMENT_ID,
        source="travel-policy.txt",
        document_type="txt",
        status=status,
        stage=stage,
        chunk_count=None,
        error_code=None,
        error_message=None,
        created_at=NOW,
        updated_at=NOW,
    )


class FakeUploadService:
    async def enqueue(self, file: object) -> IngestionJob:
        assert getattr(file, "filename") == "travel-policy.txt"
        assert await getattr(file, "read")() == "住宿标准".encode()
        return ingestion_job()


class FakeCatalogService:
    def __init__(self, document_exists: bool = True) -> None:
        self.document_exists = document_exists
        self.deleted_document_id: str | None = None

    async def list_documents(self) -> list[DocumentItem]:
        return [
            DocumentItem(
                document_id=DOCUMENT_ID,
                title="travel-policy",
                source="travel-policy.txt",
                document_type="txt",
                chunk_count=1,
                updated_at=NOW,
            )
        ]

    async def delete(self, document_id: str) -> None:
        if not self.document_exists:
            raise DocumentNotFoundError()
        self.deleted_document_id = document_id


class FakeJobs:
    def __init__(self) -> None:
        self.cancelled_job_id: str | None = None

    async def list_visible(self) -> list[IngestionJob]:
        return [ingestion_job(status="processing", stage="embedding")]

    async def get(self, job_id: str) -> SimpleNamespace:
        assert job_id == JOB_ID
        return SimpleNamespace(job=ingestion_job(status="processing", stage="embedding"))

    async def request_cancel(self, job_id: str) -> IngestionJob:
        if job_id != JOB_ID:
            raise IngestionJobNotCancellableError()
        self.cancelled_job_id = job_id
        return ingestion_job(status="cancel_requested", stage="embedding")


def create_client(
    upload_service: FakeUploadService | None = None,
    catalog_service: FakeCatalogService | None = None,
    jobs: FakeJobs | None = None,
) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_document_upload_service] = lambda: upload_service or FakeUploadService()
    app.dependency_overrides[get_document_catalog_service] = lambda: catalog_service or FakeCatalogService()
    app.dependency_overrides[get_ingestion_job_repository] = lambda: jobs or FakeJobs()
    return TestClient(app)


def test_upload_document_returns_accepted_job() -> None:
    client = create_client()

    response = client.post(
        "/api/v1/documents",
        files={"file": ("travel-policy.txt", "住宿标准", "text/plain")},
    )

    assert response.status_code == 202
    assert response.json() == {
        "job_id": JOB_ID,
        "document_id": DOCUMENT_ID,
        "source": "travel-policy.txt",
        "document_type": "txt",
        "status": "queued",
        "stage": None,
        "chunk_count": None,
        "error_code": None,
        "error_message": None,
        "created_at": "2026-08-20T00:00:00Z",
        "updated_at": "2026-08-20T00:00:00Z",
    }


def test_list_documents_returns_ready_items_only() -> None:
    client = create_client()

    response = client.get("/api/v1/documents")

    assert response.status_code == 200
    assert response.json() == [
        {
            "document_id": DOCUMENT_ID,
            "title": "travel-policy",
            "source": "travel-policy.txt",
            "document_type": "txt",
            "status": "ready",
            "chunk_count": 1,
            "updated_at": "2026-08-20T00:00:00Z",
        }
    ]


def test_delete_document_returns_no_content() -> None:
    service = FakeCatalogService()
    client = create_client(catalog_service=service)

    response = client.delete(f"/api/v1/documents/{DOCUMENT_ID}")

    assert response.status_code == 204
    assert response.content == b""
    assert service.deleted_document_id == DOCUMENT_ID


def test_delete_missing_document_returns_stable_error() -> None:
    client = create_client(catalog_service=FakeCatalogService(document_exists=False))

    response = client.delete(f"/api/v1/documents/{DOCUMENT_ID}")

    assert response.status_code == 404
    assert response.json() == {
        "code": "DOCUMENT_NOT_FOUND",
        "message": "文档不存在",
    }


def test_document_ingestions_restore_active_jobs() -> None:
    client = create_client()

    response = client.get("/api/v1/document-ingestions")

    assert response.status_code == 200
    assert response.json()[0]["status"] == "processing"
    assert response.json()[0]["stage"] == "embedding"


def test_cancel_document_ingestion_returns_cancel_requested_status() -> None:
    jobs = FakeJobs()
    client = create_client(jobs=jobs)

    response = client.post(f"/api/v1/document-ingestions/{JOB_ID}/cancel")

    assert response.status_code == 202
    assert response.json()["status"] == "cancel_requested"
    assert jobs.cancelled_job_id == JOB_ID
