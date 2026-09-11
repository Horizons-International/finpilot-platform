from abc import ABC, abstractmethod

from app.ai.schemas.requests import AIRequest
from app.ai.schemas.responses import AIResponse


class AIProvider(ABC):
    """Abstract interface for AI providers."""

    @abstractmethod
    def generate(self, request: AIRequest) -> AIResponse:
        """Process an AI request and return a standardized response."""
        raise NotImplementedError
