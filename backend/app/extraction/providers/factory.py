from app.core.config import settings
from app.extraction.exceptions import ExtractionConfigurationError
from app.extraction.providers.base import ExtractionProvider
from app.extraction.providers.mock import MockExtractionProvider


def get_extraction_provider() -> ExtractionProvider:
    provider_name = settings.EXTRACTION_PROVIDER.lower()

    if provider_name == "mock":
        return MockExtractionProvider()

    raise ExtractionConfigurationError(
        f"Unsupported extraction provider: {settings.EXTRACTION_PROVIDER}"
    )
