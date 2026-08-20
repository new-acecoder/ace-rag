import pytest

from app.core.errors import DocumentParseError, UnsupportedDocumentTypeError
from app.rag.parser import parse_document


def test_parse_utf8_markdown_normalizes_blank_lines() -> None:
    document = parse_document("travel-policy.md", "# 出差\n\n\n住宿标准\n".encode())

    assert document.title == "travel-policy"
    assert document.document_type == "md"
    assert document.content == "# 出差\n\n住宿标准"


def test_parse_rejects_unsupported_document_type() -> None:
    with pytest.raises(UnsupportedDocumentTypeError):
        parse_document("travel-policy.pdf", b"not a pdf")


def test_parse_rejects_empty_document() -> None:
    with pytest.raises(DocumentParseError):
        parse_document("empty.txt", b"\n\n")
