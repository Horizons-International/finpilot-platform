from dataclasses import dataclass
from datetime import datetime

from app.utils.enums import CommunicationStatus


@dataclass(frozen=True)
class EmailMessage:
    recipient: str
    subject: str
    body: str


@dataclass(frozen=True)
class SMSMessage:
    recipient: str
    body: str


@dataclass(frozen=True)
class CommunicationProviderResult:
    status: CommunicationStatus
    sent_at: datetime | None = None
