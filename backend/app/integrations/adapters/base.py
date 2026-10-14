"""Contracts implemented by external-service integration adapters."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.utils.enums import IntegrationStatus


@dataclass(frozen=True)
class IntegrationCheckResult:
    """Sanitized result of an adapter connectivity check."""

    status: IntegrationStatus
    message: str


class IntegrationAdapter(ABC):
    """Interface for a provider-specific integration adapter.

    Implementations should read credentials through secret references and a
    secret manager. Do not place credentials in ``configuration`` or include
    them in returned messages/exceptions.
    """

    def __init__(self, configuration: dict[str, Any]) -> None:
        self.configuration = configuration

    @abstractmethod
    def validate_configuration(self) -> None:
        """Raise ValueError when the provider configuration is invalid."""

    @abstractmethod
    def check_connection(self) -> IntegrationCheckResult:
        """Perform a bounded connectivity check and return a sanitized result."""
