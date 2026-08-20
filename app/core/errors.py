from __future__ import annotations

from pydantic import BaseModel


class ApiError(BaseModel):
    code: str
    message: str


class ApiException(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


class ServiceUnavailableError(ApiException):
    def __init__(self, service: str) -> None:
        super().__init__(503, "SERVICE_UNAVAILABLE", f"{service} 服务不可用")


class DocumentTooLargeError(ApiException):
    def __init__(self) -> None:
        super().__init__(413, "DOCUMENT_TOO_LARGE", "文件超过大小限制")


class UnsupportedDocumentTypeError(ApiException):
    def __init__(self) -> None:
        super().__init__(415, "UNSUPPORTED_DOCUMENT_TYPE", "仅支持 TXT 和 Markdown 文件")


class DocumentParseError(ApiException):
    def __init__(self) -> None:
        super().__init__(422, "DOCUMENT_PARSE_FAILED", "文档解析失败")


class DocumentIngestionError(ApiException):
    def __init__(self) -> None:
        super().__init__(500, "DOCUMENT_INGESTION_FAILED", "文档入库失败")


class DocumentNotFoundError(ApiException):
    def __init__(self) -> None:
        super().__init__(404, "DOCUMENT_NOT_FOUND", "文档不存在")


class IngestionJobNotFoundError(ApiException):
    def __init__(self) -> None:
        super().__init__(404, "INGESTION_JOB_NOT_FOUND", "摄取任务不存在")


class IngestionJobNotCancellableError(ApiException):
    def __init__(self) -> None:
        super().__init__(409, "INGESTION_JOB_NOT_CANCELLABLE", "当前摄取任务不可取消")


class IngestionCancelledError(Exception):
    pass
