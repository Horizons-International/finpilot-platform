class OCRError(Exception):
    """Base exception for OCR-related errors."""


class OCRProviderError(OCRError):
    """Raised when an OCR provider fails."""


class OCRConfigurationError(OCRError):
    """Raised when OCR provider configuration is invalid."""


class OCRResponseError(OCRError):
    """Raised when an OCR provider returns an invalid response."""
