import uuid

from app.ocr.exceptions import OCRProviderError
from app.ocr.providers.base import OCRProvider
from app.ocr.schemas.requests import OCRRequest
from app.ocr.schemas.responses import OCRResponse


class MockOCRProvider(OCRProvider):
    def process(self, request: OCRRequest) -> OCRResponse:
        if not request.file_reference:
            raise OCRProviderError("Document file reference is required.")

        return OCRResponse(
            provider_name="mock",
            document_id=request.document_id,
            extracted_text=(f"Mock OCR text extracted from {request.file_name}."),
            processing_status="completed",
            request_id=uuid.uuid4(),
        )
