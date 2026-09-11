class AIError(Exception):
    """Base exception for AI-related errors."""


class AIProviderError(AIError):
    """Raised when an AI provider fails to process a request."""


class AIConfigurationError(AIError):
    """Raised when AI provider configuration is invalid."""


class AIResponseError(AIError):
    """Raised when an AI provider returns an invalid response."""
