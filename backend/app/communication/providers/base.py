from abc import ABC, abstractmethod

from app.communication.schemas import (
    CommunicationProviderResult,
    EmailMessage,
    SMSMessage,
)


class EmailProvider(ABC):
    @abstractmethod
    def send(
        self,
        message: EmailMessage,
    ) -> CommunicationProviderResult:
        raise NotImplementedError


class SMSProvider(ABC):
    @abstractmethod
    def send(
        self,
        message: SMSMessage,
    ) -> CommunicationProviderResult:
        raise NotImplementedError
