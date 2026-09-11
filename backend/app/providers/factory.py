from app.core.config import settings
from app.providers.mock_provider import MockVerificationProvider
from app.providers.verification_provider import (
    VerificationProvider,
)


def get_verification_provider() -> VerificationProvider:
    if settings.VERIFICATION_PROVIDER == "mock":
        return MockVerificationProvider()

    raise ValueError(
        f"Unsupported verification provider: {settings.VERIFICATION_PROVIDER}"
    )
