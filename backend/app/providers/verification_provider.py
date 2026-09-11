from abc import ABC, abstractmethod

from app.providers.schemas import (
    VerificationRequest,
    VerificationResponse,
)


class VerificationProvider(ABC):
    @abstractmethod
    def verify(
        self,
        request: VerificationRequest,
    ) -> VerificationResponse:
        """Submit a verification request to the provider."""
        raise NotImplementedError
