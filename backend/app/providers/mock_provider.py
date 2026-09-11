import uuid

from app.providers.schemas import (
    VerificationRequest,
    VerificationResponse,
)
from app.providers.verification_provider import (
    VerificationProvider,
)
from app.utils.enums import VerificationStatus


class MockVerificationProvider(VerificationProvider):
    def verify(
        self,
        request: VerificationRequest,
    ) -> VerificationResponse:
        return VerificationResponse(
            provider_name="mock",
            verification_case_id=request.verification_case_id,
            status=VerificationStatus.UNDER_REVIEW,
            reference_id=str(uuid.uuid4()),
            message=("Verification request accepted by the mock provider."),
        )
