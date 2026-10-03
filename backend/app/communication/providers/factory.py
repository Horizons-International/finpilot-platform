from app.communication.exceptions import CommunicationConfigurationError
from app.communication.providers.base import EmailProvider, SMSProvider
from app.communication.providers.mock import MockEmailProvider, MockSMSProvider
from app.core.config import settings


def get_email_provider() -> EmailProvider:
    provider_name = settings.EMAIL_PROVIDER.lower()

    if provider_name == "mock":
        return MockEmailProvider()

    raise CommunicationConfigurationError(
        f"Unsupported email provider: {provider_name}",
    )


def get_sms_provider() -> SMSProvider:
    provider_name = settings.SMS_PROVIDER.lower()

    if provider_name == "mock":
        return MockSMSProvider()

    raise CommunicationConfigurationError(
        f"Unsupported SMS provider: {provider_name}",
    )
