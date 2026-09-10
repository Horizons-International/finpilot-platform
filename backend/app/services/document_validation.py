from pathlib import Path

from app.core.config import settings
from app.utils.constants import DOCUMENT_ALLOWED_FILE_TYPES
from app.utils.errors import bad_request


class DocumentValidationService:
    """Validates technical requirements for verification documents."""

    @staticmethod
    def validate_file_type(content_type: str | None) -> None:
        if not content_type:
            raise bad_request("File content type is required.")

        if content_type not in DOCUMENT_ALLOWED_FILE_TYPES:
            raise bad_request(
                "Unsupported document file type. "
                "Only PDF, JPG, and PNG files are allowed."
            )

    @staticmethod
    def validate_file_size(file_size: int) -> None:
        if file_size > settings.MAX_FILE_SIZE:
            raise bad_request("Document file size exceeds the maximum allowed size.")

    @staticmethod
    def validate_file_name(filename: str | None) -> None:
        if not filename:
            raise bad_request("Filename is required.")

        if Path(filename).name != filename:
            raise bad_request("Invalid filename.")

        if any(
            not (character.isalnum() or character in {" ", ".", "_", "-"})
            for character in filename
        ):
            raise bad_request("Filename contains unsupported characters.")

    @staticmethod
    def validate_document_type(document_type_id: object | None) -> None:
        if document_type_id is None:
            raise bad_request("Document type is required.")

    @classmethod
    def validate(
        cls,
        *,
        filename: str | None,
        content_type: str | None,
        file_size: int,
        document_type_id: object | None,
    ) -> None:
        cls.validate_file_name(filename)
        cls.validate_file_type(content_type)
        cls.validate_file_size(file_size)
        cls.validate_document_type(document_type_id)
