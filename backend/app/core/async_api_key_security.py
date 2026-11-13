"""Async API-key authentication with explicit tenant and permission checks."""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Callable
from typing import Any

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_key_security import APIKeyPrincipal
from app.core.database import get_async_db
from app.models.api_key import APIKey
from app.models.tenant import Tenant
from app.services.async_subscription_service import (
    is_billing_exempt_path,
    record_subscription_usage,
)
from app.utils.enums import APIKeyStatus, TenantStatus


def _unauthorized(message: str = "Invalid or revoked API key.") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=message,
        headers={"WWW-Authenticate": "ApiKey"},
    )


def require_async_api_key_permission(permission: str) -> Callable[..., Any]:
    """Resolve a globally unique key hash, then bind the session to its tenant."""

    async def authenticate_api_key(
        request: Request,
        api_key_value: str | None = Header(default=None, alias="X-API-Key"),
        db: AsyncSession = Depends(get_async_db),
    ) -> APIKeyPrincipal:
        if not api_key_value or len(api_key_value) > 512:
            raise _unauthorized("An X-API-Key header is required.")
        digest = hashlib.sha256(api_key_value.encode("utf-8")).hexdigest()
        key = await db.scalar(
            select(APIKey)
            .where(APIKey.key_hash == digest)
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason=(
                    "resolve globally unique API key before tenant context is known"
                ),
            )
        )
        if (
            key is None
            or not hmac.compare_digest(key.key_hash, digest)
            or key.status != APIKeyStatus.ACTIVE
        ):
            raise _unauthorized()
        previous = db.info.get("tenant_id")
        if previous is not None and previous != key.tenant_id:
            raise _unauthorized()
        db.info["tenant_id"] = key.tenant_id
        tenant = await db.scalar(select(Tenant).where(Tenant.id == key.tenant_id))
        if tenant is None or tenant.status != TenantStatus.ACTIVE:
            raise _unauthorized("The API key tenant is not active.")
        request.state.api_key_id = key.id
        request.state.api_key_tenant_id = key.tenant_id
        if permission not in set(key.permissions or []):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="The API key does not have the required permission.",
            )
        if not is_billing_exempt_path(request.url.path):
            await record_subscription_usage(db, key.tenant_id, "api_calls")
        return APIKeyPrincipal(
            api_key_id=key.id,
            tenant_id=key.tenant_id,
            permissions=frozenset(key.permissions or []),
            name=key.name,
        )

    return authenticate_api_key
