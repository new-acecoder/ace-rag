from __future__ import annotations

import re
from datetime import datetime
from uuid import uuid4

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.rag.schemas import IngestionChunk, ParsedDocument

_MARKDOWN_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_SEPARATORS = ["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""]


def split_document(
    document: ParsedDocument,
    document_id: str,
    updated_at: datetime,
    chunk_size: int,
    chunk_overlap: int,
) -> list[IngestionChunk]:
    sections = (
        _markdown_sections(document.content)
        if document.document_type == "md"
        else [("", document.content)]
    )
    chunk_texts: list[str] = []

    for heading_path, content in sections:
        chunk_texts.extend(_split_section(content, heading_path, chunk_size, chunk_overlap))

    return [
        IngestionChunk(
            document_id=document_id,
            chunk_id=str(uuid4()),
            chunk_index=index,
            chunk_count=len(chunk_texts),
            content=content,
            title=document.title,
            page_number=None,
            source=document.source,
            document_type=document.document_type,
            version="1",
            updated_at=updated_at,
        )
        for index, content in enumerate(chunk_texts)
    ]


def _split_section(
    content: str, heading_path: str, chunk_size: int, chunk_overlap: int
) -> list[str]:
    prefix = f"{heading_path}\n\n" if heading_path else ""
    content_budget = max(1, chunk_size - len(prefix))
    overlap = min(chunk_overlap, max(0, content_budget - 1))
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=content_budget,
        chunk_overlap=overlap,
        separators=_SEPARATORS,
    )
    return [f"{prefix}{part}".strip() for part in splitter.split_text(content) if part.strip()]


def _markdown_sections(content: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    headings: list[str] = []
    current_lines: list[str] = []

    def flush() -> None:
        section_content = "\n".join(current_lines).strip()
        non_blank_lines = [line for line in current_lines if line.strip()]
        is_heading_only = bool(non_blank_lines) and all(
            _MARKDOWN_HEADING.match(line) is not None for line in non_blank_lines
        )
        if section_content and not is_heading_only:
            sections.append((" > ".join(headings), section_content))

    for line in content.split("\n"):
        match = _MARKDOWN_HEADING.match(line)
        if match is None:
            current_lines.append(line)
            continue

        flush()
        level = len(match.group(1))
        headings = headings[: level - 1]
        headings.append(match.group(2))
        current_lines = [line]

    flush()
    return sections
