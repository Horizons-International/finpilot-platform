class CommunicationError(Exception):
    """Base exception for communication-related errors."""


class CommunicationProviderError(CommunicationError):
    """Raised when a communication provider fails."""


class CommunicationConfigurationError(CommunicationError):
    """Raised when communication provider configuration is invalid."""
