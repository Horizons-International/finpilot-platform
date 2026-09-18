from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.rag import extraction
from app.rag.extraction import extract_text


def test_extract_text_from_plain_text():
    content = b"  First line.\n\nSecond line.  "

    result = extract_text(
        content=content,
        filename="policy.txt",
        content_type="text/plain",
    )

    assert result == "First line.\n\nSecond line."


def test_extract_text_normalizes_surrounding_whitespace():
    content = b"\n\n  Customer verification policy.  \n\n"

    result = extract_text(
        content=content,
        filename="policy.txt",
        content_type="text/plain",
    )

    assert result == "Customer verification policy."


def test_extract_text_supports_unicode():
    content = "Customer verification — required document.".encode("utf-8")

    result = extract_text(
        content=content,
        filename="policy.txt",
        content_type="text/plain",
    )

    assert "verification" in result
    assert "required" in result


def test_extract_text_from_plain_text_with_invalid_utf8():
    content = b"Valid text \xff invalid byte"

    result = extract_text(
        content=content,
        filename="policy.txt",
        content_type="text/plain",
    )

    assert result == "Valid text \ufffd invalid byte"


def test_extract_text_requires_filename():
    with pytest.raises(HTTPException) as exc_info:
        extract_text(
            content=b"Some text",
            filename="",
            content_type="text/plain",
        )

    assert "Filename is required." in str(exc_info.value)
    assert exc_info.value.status_code == 400


def test_extract_text_rejects_empty_content():
    with pytest.raises(HTTPException) as exc_info:
        extract_text(
            content=b"",
            filename="policy.txt",
            content_type="text/plain",
        )

    assert "uploaded document is empty" in str(exc_info.value)
    assert exc_info.value.status_code == 400


def test_extract_text_rejects_unsupported_file_type():
    with pytest.raises(HTTPException) as exc_info:
        extract_text(
            content=b"Some text",
            filename="policy.docx",
            content_type=(
                "application/vnd.openxmlformats-officedocument"
                ".wordprocessingml.document"
            ),
        )

    assert "Text extraction is not supported" in str(exc_info.value)
    assert exc_info.value.status_code == 400


def test_extract_text_rejects_document_with_no_extractable_text():
    with pytest.raises(HTTPException) as exc_info:
        extract_text(
            content=b"   \n\t   ",
            filename="empty.txt",
            content_type="text/plain",
        )

    assert "No extractable text was found" in str(exc_info.value)
    assert exc_info.value.status_code == 400


def test_extract_text_from_pdf(monkeypatch):
    fake_page_1 = SimpleNamespace(
        extract_text=lambda: "First page text",
    )
    fake_page_2 = SimpleNamespace(
        extract_text=lambda: "Second page text",
    )

    fake_reader = SimpleNamespace(
        pages=[fake_page_1, fake_page_2],
    )

    monkeypatch.setattr(
        extraction,
        "PdfReader",
        lambda _: fake_reader,
    )

    result = extract_text(
        content=b"fake pdf content",
        filename="policy.pdf",
        content_type="application/pdf",
    )

    assert result == "First page text\n\nSecond page text"


def test_extract_text_pdf_ignores_pages_without_text(monkeypatch):
    fake_page_1 = SimpleNamespace(
        extract_text=lambda: "First page",
    )
    fake_page_2 = SimpleNamespace(
        extract_text=lambda: None,
    )
    fake_page_3 = SimpleNamespace(
        extract_text=lambda: "Third page",
    )

    fake_reader = SimpleNamespace(
        pages=[fake_page_1, fake_page_2, fake_page_3],
    )

    monkeypatch.setattr(
        extraction,
        "PdfReader",
        lambda _: fake_reader,
    )

    result = extract_text(
        content=b"fake pdf content",
        filename="policy.pdf",
        content_type="application/pdf",
    )

    assert result == "First page\n\nThird page"


def test_extract_text_pdf_error_is_converted_to_bad_request(monkeypatch):
    def raise_error(_):
        raise RuntimeError("PDF parsing failed")

    monkeypatch.setattr(
        extraction,
        "PdfReader",
        raise_error,
    )

    with pytest.raises(HTTPException) as exc_info:
        extract_text(
            content=b"invalid pdf",
            filename="broken.pdf",
            content_type="application/pdf",
        )

    assert "Unable to extract text from the PDF." in str(exc_info.value)
    assert exc_info.value.status_code == 400


def test_extract_text_pdf_with_no_text_is_rejected(monkeypatch):
    fake_page = SimpleNamespace(
        extract_text=lambda: None,
    )

    fake_reader = SimpleNamespace(
        pages=[fake_page],
    )

    monkeypatch.setattr(
        extraction,
        "PdfReader",
        lambda _: fake_reader,
    )

    with pytest.raises(HTTPException) as exc_info:
        extract_text(
            content=b"fake pdf content",
            filename="image-only.pdf",
            content_type="application/pdf",
        )

    assert "No extractable text was found" in str(exc_info.value)
    assert exc_info.value.status_code == 400
