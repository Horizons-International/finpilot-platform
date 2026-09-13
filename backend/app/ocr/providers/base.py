from abc import ABC, abstractmethod

from app.ocr.schemas.requests import OCRRequest
from app.ocr.schemas.responses import OCRResponse


class OCRProvider(ABC):
    @abstractmethod
    def process(self, request: OCRRequest) -> OCRResponse:
        raise NotImplementedError
