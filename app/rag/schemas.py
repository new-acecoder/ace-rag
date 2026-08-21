from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

DocumentType = Literal["txt", "md"]
IngestionStatus = Literal[
    "queued",
    "processing",
    "ready",
    "failed",
    "cancel_requested",
    "cancelled",
]
IngestionStage = Literal["parsing", "splitting", "embedding", "indexing"]


class RetrievedChunk(BaseModel):
    document_id: str
    chunk_id: str
    chunk_index: int
    content: str
    title: str
    page_number: int | None
    source: str
    document_type: DocumentType
    version: str | None
    updated_at: datetime
    score: float | None = None


class Source(BaseModel):
    citation_index: int
    document_id: str
    chunk_id: str
    title: str
    page_number: int | None
    source: str
    document_type: DocumentType


class DocumentInfo(BaseModel):
    document_id: str
    title: str
    version: str | None
    source: str
    document_type: DocumentType
    updated_at: datetime


class DocumentItem(BaseModel):
    document_id: str
    title: str
    source: str
    document_type: DocumentType
    status: Literal["ready"] = "ready"
    chunk_count: int
    updated_at: datetime


class IngestionJob(BaseModel):
    job_id: str
    document_id: str
    source: str
    document_type: DocumentType
    status: IngestionStatus
    stage: IngestionStage | None
    chunk_count: int | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    title: str
    source: str
    document_type: DocumentType
    content: str


@dataclass(frozen=True, slots=True)
class IngestionChunk:
    document_id: str
    chunk_id: str
    chunk_index: int
    chunk_count: int
    content: str
    title: str
    page_number: int | None
    source: str
    document_type: DocumentType
    version: str
    updated_at: datetime
