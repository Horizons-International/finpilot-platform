"""Sandbox-only API-key authentication and feature enablement."""

import hashlib
import hmac
from collections.abc import Callable, Generator
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.sandbox import SandboxAccount
from app.repositories.sandbox_repository import SandboxRepository
from app.utils.date_time import utc_now


@dataclass(frozen=True)
class SandboxPrincipal:
    account_id: UUID
    api_key_id: UUID
    permissions: frozenset[str]


def require_sandbox_enabled() -> None:
    if not getattr(settings, "SANDBOX_ENABLED", False):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sandbox API is not enabled on this deployment.",
        )


def require_sandbox_permission(
    permission: str,
) -> Callable[..., Generator[SandboxPrincipal, None, None]]:
    """Authenticate a prefixed, hashed sandbox key and require one exact scope."""

    def authenticate(
        request: Request,
        api_key_value: str | None = Header(default=None, alias="X-API-Key"),
        db: Session = Depends(get_db),
    ) -> Generator[SandboxPrincipal, None, None]:
        if (
            not api_key_value
            or not api_key_value.startswith("fp_test_")
            or len(api_key_value) > 512
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="A valid X-API-Key sandbox key is required.",
                headers={"WWW-Authenticate": "ApiKey"},
            )
        digest = hashlib.sha256(api_key_value.encode("utf-8")).hexdigest()
        key = SandboxRepository(db).get_key_by_hash(digest)
        if (
            key is None
            or not hmac.compare_digest(key.key_hash, digest)
            or key.status != "ACTIVE"
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or revoked sandbox API key.",
                headers={"WWW-Authenticate": "ApiKey"},
            )
        account = db.get(SandboxAccount, key.sandbox_account_id)
        if (
            account is None
            or account.status != "ACTIVE"
            or account.expires_at <= utc_now()
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Sandbox account is inactive or expired.",
            )
        permissions = frozenset(key.permissions or [])
        if permission not in permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Sandbox API key requires permission '{permission}'.",
            )
        key.last_used_at = utc_now()
        db.commit()
        request.state.sandbox_account_id = account.id
        request.state.sandbox_api_key_id = key.id
        # No production tenant/user identity is assigned to this request.
        yield SandboxPrincipal(
            account_id=account.id,
            api_key_id=key.id,
            permissions=permissions,
        )

    return authenticate
