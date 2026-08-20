from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Response, UploadFile, status

from app.cache.retrieval_cache import RetrievalCache
from app.core.config import Settings, get_settings
from app.ingestion.jobs import IngestionJobRepository
from app.ingestion.services import DocumentCatalogService, DocumentUploadService
from app.rag.milvus import MilvusChunkRepository
from app.rag.schemas import DocumentItem, IngestionJob
from app.storage.document_objects import DocumentObjectStore

router = APIRouter(prefix="/api/v1", tags=["documents"])


def get_document_upload_service(
    settings: Settings = Depends(get_settings),
) -> DocumentUploadService:
    return DocumentUploadService(
        settings=settings,
        object_store=DocumentObjectStore(settings),
        jobs=IngestionJobRepository(settings),
    )


def get_document_catalog_service(
    settings: Settings = Depends(get_settings),
) -> DocumentCatalogService:
    return DocumentCatalogService(
        repository=MilvusChunkRepository(settings),
        object_store=DocumentObjectStore(settings),
        jobs=IngestionJobRepository(settings),
        retrieval_cache=RetrievalCache(settings),
    )


def get_ingestion_job_repository(
    settings: Settings = Depends(get_settings),
) -> IngestionJobRepository:
    return IngestionJobRepository(settings)


@router.post("/documents", response_model=IngestionJob, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: UploadFile = File(...),
    service: DocumentUploadService = Depends(get_document_upload_service),
) -> IngestionJob:
    return await service.enqueue(file)


@router.get("/documents", response_model=list[DocumentItem])
async def list_documents(
    service: DocumentCatalogService = Depends(get_document_catalog_service),
) -> list[DocumentItem]:
    return await service.list_documents()


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID,
    service: DocumentCatalogService = Depends(get_document_catalog_service),
) -> Response:
    await service.delete(str(document_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/document-ingestions", response_model=list[IngestionJob])
async def list_document_ingestions(
    repository: IngestionJobRepository = Depends(get_ingestion_job_repository),
) -> list[IngestionJob]:
    return await repository.list_visible()


@router.get("/document-ingestions/{job_id}", response_model=IngestionJob)
async def get_document_ingestion(
    job_id: UUID,
    repository: IngestionJobRepository = Depends(get_ingestion_job_repository),
) -> IngestionJob:
    return (await repository.get(str(job_id))).job


@router.post(
    "/document-ingestions/{job_id}/cancel",
    response_model=IngestionJob,
    status_code=status.HTTP_202_ACCEPTED,
)
async def cancel_document_ingestion(
    job_id: UUID,
    repository: IngestionJobRepository = Depends(get_ingestion_job_repository),
) -> IngestionJob:
    return await repository.request_cancel(str(job_id))
