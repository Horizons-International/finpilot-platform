"""API-key authentication for explicitly permissioned partner endpoints.

API keys are not converted into user sessions and never inherit a user's role.
Each partner endpoint must request an exact permission with
``require_api_key_permission``.
"""

import hashlib
import hmac
from collections.abc import Callable, Generator
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.api_key import APIKey
from app.models.tenant import Tenant
from app.utils.enums import APIKeyStatus, TenantStatus


@dataclass(frozen=True)
class APIKeyPrincipal:
    api_key_id: UUID
    tenant_id: UUID
    permissions: frozenset[str]
    name: str


def _unauthorized(message: str = "Invalid or revoked API key.") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=message,
        headers={"WWW-Authenticate": "ApiKey"},
    )


def require_api_key_permission(
    permission: str,
) -> Callable[..., Generator[APIKeyPrincipal, None, None]]:
    """Require an active key with one exact permission."""

    def authenticate_api_key(
        request: Request,
        api_key_value: str | None = Header(default=None, alias="X-API-Key"),
        db: Session = Depends(get_db),
    ) -> Generator[APIKeyPrincipal, None, None]:
        if not api_key_value or len(api_key_value) > 512:
            raise _unauthorized("An X-API-Key header is required.")

        digest = hashlib.sha256(api_key_value.encode("utf-8")).hexdigest()
        api_key = db.scalar(
            select(APIKey)
            .where(APIKey.key_hash == digest)
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason=(
                    "resolve a globally unique API-key hash before its tenant "
                    "context is known"
                ),
            )
        )
        if (
            api_key is None
            or not hmac.compare_digest(api_key.key_hash, digest)
            or api_key.status != APIKeyStatus.ACTIVE
        ):
            raise _unauthorized()

        previous_tenant_id = db.info.get("tenant_id")
        if previous_tenant_id is not None and previous_tenant_id != api_key.tenant_id:
            raise _unauthorized()
        db.info["tenant_id"] = api_key.tenant_id

        tenant = db.scalar(select(Tenant).where(Tenant.id == api_key.tenant_id))
        if tenant is None or tenant.status != TenantStatus.ACTIVE:
            raise _unauthorized("The API key tenant is not active.")

        # These values are trusted only after hash, status, and tenant checks.
        # APIKeyUsageMiddleware uses them after the actual HTTP status is known.
        request.state.api_key_id = api_key.id
        request.state.api_key_tenant_id = api_key.tenant_id

        if permission not in set(api_key.permissions or []):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="The API key does not have the required permission.",
            )

        yield APIKeyPrincipal(
            api_key_id=api_key.id,
            tenant_id=api_key.tenant_id,
            permissions=frozenset(api_key.permissions or []),
            name=api_key.name,
        )

    return authenticate_api_key
