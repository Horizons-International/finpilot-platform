class ExtractionError(Exception):
    """Base exception for document extraction errors."""


class ExtractionProviderError(ExtractionError):
    """Raised when the extraction provider fails."""


class ExtractionResponseError(ExtractionError):
    """Raised when the extraction provider returns invalid data."""


class ExtractionConfigurationError(ExtractionError):
    """Raised when extraction is incorrectly configured."""
