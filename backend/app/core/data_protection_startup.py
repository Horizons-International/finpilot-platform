"""Deployment checks for encryption keys, database TLS, and HTTPS ingress."""

from urllib.parse import parse_qs, urlsplit

from cryptography.fernet import Fernet

from app.core.config import settings


def validate_data_protection_environment() -> None:
    """Call during FastAPI lifespan/startup before serving production traffic."""
    if settings.ENVIRONMENT not in {"staging", "production"}:
        return

    if not settings.DATA_PROTECTION_KEY:
        raise RuntimeError("DATA_PROTECTION_KEY must be set in production")
    try:
        Fernet(settings.DATA_PROTECTION_KEY.encode("ascii"))
    except (ValueError, TypeError, UnicodeEncodeError) as exc:
        raise RuntimeError("DATA_PROTECTION_KEY is not a valid Fernet key") from exc

    if settings.DATABASE_REQUIRE_SSL:
        query = parse_qs(urlsplit(settings.DATABASE_URL).query)
        sslmode = (query.get("sslmode") or [""])[0].casefold()
        if sslmode not in {"require", "verify-ca", "verify-full"}:
            raise RuntimeError(
                "Production DATABASE_URL must specify "
                "sslmode=require, verify-ca, or verify-full"
            )

    if (
        settings.HTTPS_REQUIRED_IN_PRODUCTION
        and not settings.PUBLIC_BASE_URL.lower().startswith("https://")
    ):
        raise RuntimeError("PUBLIC_BASE_URL must use https:// in production")
