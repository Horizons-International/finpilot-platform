from app.core.config import settings
from app.ocr.exceptions import OCRConfigurationError
from app.ocr.providers.base import OCRProvider
from app.ocr.providers.mock import MockOCRProvider


def get_ocr_provider() -> OCRProvider:
    provider_name = settings.OCR_PROVIDER.lower()

    if provider_name == "mock":
        return MockOCRProvider()

    raise OCRConfigurationError(f"Unsupported OCR provider: {settings.OCR_PROVIDER}")
