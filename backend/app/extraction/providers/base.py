from abc import ABC, abstractmethod
from uuid import UUID

from app.extraction.schemas.responses import DocumentExtractionResponse


class ExtractionProvider(ABC):
    """Interface for document information extraction providers."""

    @abstractmethod
    def extract(
        self,
        *,
        document_id: UUID,
        ocr_text: str,
    ) -> DocumentExtractionResponse:
        raise NotImplementedError
