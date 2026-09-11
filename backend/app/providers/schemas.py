from dataclasses import dataclass
from uuid import UUID

from app.utils.enums import VerificationStatus, VerificationType


@dataclass
class VerificationRequest:
    customer_id: UUID
    verification_case_id: UUID
    verification_type: VerificationType


@dataclass
class VerificationResponse:
    provider_name: str
    verification_case_id: UUID
    status: VerificationStatus
    reference_id: str
    message: str | None = None


@dataclass(frozen=True)
class VerificationProviderConfig:
    provider_name: str
    timeout_seconds: int = 30
