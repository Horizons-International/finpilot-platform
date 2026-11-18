"""Async sandbox API-key authentication and feature enablement."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any, Callable
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_async_db
from app.models.sandbox import SandboxAccount
from app.repositories.async_sandbox_repository import AsyncSandboxRepository
from app.utils.date_time import utc_now


@dataclass(frozen=True)
class AsyncSandboxPrincipal:
    account_id: UUID
    api_key_id: UUID
    permissions: frozenset[str]


def require_sandbox_enabled() -> None:
    if not getattr(settings, "SANDBOX_ENABLED", False):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sandbox API is not enabled on this deployment.",
        )


def require_async_sandbox_permission(permission: str) -> Callable[..., Any]:
    """Validate a sandbox API key without opening a synchronous DB session."""

    async def authenticate(
        request: Request,
        api_key_value: str | None = Header(default=None, alias="X-API-Key"),
        db: AsyncSession = Depends(get_async_db),
    ) -> AsyncSandboxPrincipal:
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
        key = await AsyncSandboxRepository(db).get_key_by_hash(digest)
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
        account = await db.get(SandboxAccount, key.sandbox_account_id)
        now = utc_now()
        if account is None or account.status != "ACTIVE" or account.expires_at <= now:
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
        key.last_used_at = now
        account_id = account.id
        api_key_id = key.id
        await db.commit()
        request.state.sandbox_account_id = account_id
        request.state.sandbox_api_key_id = api_key_id
        return AsyncSandboxPrincipal(
            account_id=account_id,
            api_key_id=api_key_id,
            permissions=permissions,
        )

    return authenticate
