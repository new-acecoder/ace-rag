from __future__ import annotations

from pathlib import Path

from app.core.errors import DocumentParseError, UnsupportedDocumentTypeError
from app.rag.schemas import DocumentType, ParsedDocument

_DOCUMENT_TYPES: dict[str, DocumentType] = {".txt": "txt", ".md": "md"}


def get_document_type(filename: str | None) -> DocumentType:
    suffix = Path(filename or "").suffix.lower()
    document_type = _DOCUMENT_TYPES.get(suffix)
    if document_type is None:
        raise UnsupportedDocumentTypeError()
    return document_type


def parse_document(filename: str | None, content: bytes) -> ParsedDocument:
    document_type = get_document_type(filename)

    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise DocumentParseError() from error

    normalized = normalize_text(decoded)
    if not normalized:
        raise DocumentParseError()

    title = Path(filename or "").stem.strip()
    if not title:
        raise DocumentParseError()

    return ParsedDocument(
        title=title,
        source=filename or "",
        document_type=document_type,
        content=normalized,
    )


def normalize_text(content: str) -> str:
    lines = (
        content.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\x00", "")
        .split("\n")
    )
    normalized_lines: list[str] = []
    previous_blank = False

    for line in lines:
        line = line.rstrip()
        if not line:
            if previous_blank:
                continue
            previous_blank = True
        else:
            previous_blank = False
        normalized_lines.append(line)

    return "\n".join(normalized_lines).strip()
