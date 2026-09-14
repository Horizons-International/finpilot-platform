from uuid import UUID

from app.extraction.exceptions import ExtractionProviderError
from app.extraction.providers.base import ExtractionProvider
from app.extraction.schemas.responses import DocumentExtractionResponse


class MockExtractionProvider(ExtractionProvider):
    """Mock extraction provider for development and testing."""

    def __init__(
        self,
        response: DocumentExtractionResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.document_ids: list[UUID] = []
        self.ocr_texts: list[str] = []

    def extract(
        self,
        *,
        document_id: UUID,
        ocr_text: str,
    ) -> DocumentExtractionResponse:
        self.document_ids.append(document_id)
        self.ocr_texts.append(ocr_text)

        if self.error is not None:
            raise self.error

        if self.response is None:
            raise ExtractionProviderError(
                "Mock extraction provider has no configured response."
            )

        return self.response
