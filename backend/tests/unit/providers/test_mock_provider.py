import uuid

from app.providers.mock_provider import MockVerificationProvider
from app.providers.schemas import VerificationRequest
from app.utils.enums import VerificationStatus, VerificationType


def test_mock_provider_returns_verification_response():
    provider = MockVerificationProvider()

    customer_id = uuid.uuid4()
    verification_case_id = uuid.uuid4()

    request = VerificationRequest(
        customer_id=customer_id,
        verification_case_id=verification_case_id,
        verification_type=VerificationType.IDENTITY,
    )

    response = provider.verify(request)

    assert response.provider_name == "mock"
    assert response.verification_case_id == verification_case_id
    assert response.status == VerificationStatus.UNDER_REVIEW
    assert response.reference_id
    assert response.message == ("Verification request accepted by the mock provider.")


def test_mock_provider_returns_unique_reference_id():
    provider = MockVerificationProvider()

    request = VerificationRequest(
        customer_id=uuid.uuid4(),
        verification_case_id=uuid.uuid4(),
        verification_type=VerificationType.IDENTITY,
    )

    first_response = provider.verify(request)
    second_response = provider.verify(request)

    assert first_response.reference_id != second_response.reference_id
