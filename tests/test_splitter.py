from datetime import UTC, datetime

from app.rag.schemas import ParsedDocument
from app.rag.splitter import split_document


def test_markdown_splitter_preserves_heading_path_and_chunk_metadata() -> None:
    document = ParsedDocument(
        title="travel-policy",
        source="travel-policy.md",
        document_type="md",
        content="# 出差\n## 住宿\n" + "住宿费用按照城市标准报销。" * 20,
    )

    chunks = split_document(
        document=document,
        document_id="document-1",
        updated_at=datetime(2026, 8, 20, tzinfo=UTC),
        chunk_size=80,
        chunk_overlap=12,
    )

    assert len(chunks) > 1
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert {chunk.chunk_count for chunk in chunks} == {len(chunks)}
    assert all("出差 > 住宿" in chunk.content for chunk in chunks)
    assert all(chunk.page_number is None for chunk in chunks)
