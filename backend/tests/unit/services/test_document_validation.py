import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.services.document_validation import DocumentValidationService


def test_accepts_pdf_file_type():
    DocumentValidationService.validate_file_type("application/pdf")


def test_accepts_jpeg_file_type():
    DocumentValidationService.validate_file_type("image/jpeg")


def test_accepts_png_file_type():
    DocumentValidationService.validate_file_type("image/png")


def test_rejects_unsupported_file_type():
    with pytest.raises(HTTPException) as exc_info:
        DocumentValidationService.validate_file_type("text/plain")

    assert exc_info.value.status_code == 400
    assert (
        exc_info.value.detail == "Unsupported document file type. "
        "Only PDF, JPG, and PNG files are allowed."
    )


def test_rejects_missing_file_type():
    with pytest.raises(HTTPException) as exc_info:
        DocumentValidationService.validate_file_type(None)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "File content type is required."


def test_accepts_file_size_below_maximum():
    DocumentValidationService.validate_file_size(settings.MAX_FILE_SIZE - 1)


def test_accepts_file_size_at_maximum():
    DocumentValidationService.validate_file_size(settings.MAX_FILE_SIZE)


def test_rejects_file_size_above_maximum():
    with pytest.raises(HTTPException) as exc_info:
        DocumentValidationService.validate_file_size(settings.MAX_FILE_SIZE + 1)

    assert exc_info.value.status_code == 400
    assert (
        exc_info.value.detail == "Document file size exceeds the maximum allowed size."
    )


@pytest.mark.parametrize(
    "filename",
    [
        "passport.pdf",
        "passport-2026.pdf",
        "passport_2026.pdf",
        "my passport.pdf",
        "national.id.png",
        "document123.jpg",
    ],
)
def test_accepts_valid_filename(filename: str):
    DocumentValidationService.validate_file_name(filename)


@pytest.mark.parametrize(
    "filename",
    [
        "../../passport.pdf",
        "../passport.pdf",
        "documents/passport.pdf",
        "folder\\passport.pdf",
        "passport@2026.pdf",
        "passport#2026.pdf",
        "passport$2026.pdf",
        "passport%2026.pdf",
        "passport*2026.pdf",
        "passport?.pdf",
    ],
)
def test_rejects_invalid_filename(filename: str):
    with pytest.raises(HTTPException) as exc_info:
        DocumentValidationService.validate_file_name(filename)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail in (
        "Invalid filename.",
        "Filename contains unsupported characters.",
    )


def test_rejects_missing_filename():
    with pytest.raises(HTTPException) as exc_info:
        DocumentValidationService.validate_file_name(None)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Filename is required."


def test_accepts_document_type():
    document_type_id = "00000000-0000-0000-0000-000000000001"

    DocumentValidationService.validate_document_type(document_type_id)


def test_rejects_missing_document_type():
    with pytest.raises(HTTPException) as exc_info:
        DocumentValidationService.validate_document_type(None)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Document type is required."


def test_accepts_valid_document():
    DocumentValidationService.validate(
        filename="passport.pdf",
        content_type="application/pdf",
        file_size=1024,
        document_type_id="00000000-0000-0000-0000-000000000001",
    )


def test_rejects_invalid_document_type():
    with pytest.raises(HTTPException) as exc_info:
        DocumentValidationService.validate(
            filename="passport.pdf",
            content_type="application/zip",
            file_size=1024,
            document_type_id="00000000-0000-0000-0000-000000000001",
        )

    assert exc_info.value.status_code == 400


def test_rejects_oversized_document():
    with pytest.raises(HTTPException) as exc_info:
        DocumentValidationService.validate(
            filename="passport.pdf",
            content_type="application/pdf",
            file_size=settings.MAX_FILE_SIZE + 1,
            document_type_id="00000000-0000-0000-0000-000000000001",
        )

    assert exc_info.value.status_code == 400


def test_rejects_invalid_document_filename():
    with pytest.raises(HTTPException) as exc_info:
        DocumentValidationService.validate(
            filename="passport@2026.pdf",
            content_type="application/pdf",
            file_size=1024,
            document_type_id="00000000-0000-0000-0000-000000000001",
        )

    assert exc_info.value.status_code == 400


def test_rejects_missing_document_type_from_full_validation():
    with pytest.raises(HTTPException) as exc_info:
        DocumentValidationService.validate(
            filename="passport.pdf",
            content_type="application/pdf",
            file_size=1024,
            document_type_id=None,
        )

    assert exc_info.value.status_code == 400
