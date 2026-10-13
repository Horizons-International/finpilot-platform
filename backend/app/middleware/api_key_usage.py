"""Record API-key usage after FastAPI has produced the final HTTP response."""

import inspect
from collections.abc import Callable, Generator
from typing import Any, cast
from uuid import UUID

from fastapi import Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from app.core.database import SessionLocal, get_db
from app.core.logger import get_logger
from app.models.api_key import APIKey, APIKeyUsage
from app.utils.date_time import utc_now

logger = get_logger(__name__)


def _open_usage_session(request: Request) -> tuple[Session, Callable[[], Any]]:
    """Use the application's normal session; honor test dependency overrides too."""
    overrides = getattr(request.app, "dependency_overrides", {})
    override_factory = overrides.get(get_db)
    if override_factory is not None:
        provided = override_factory()
        if inspect.isgenerator(provided):
            generator = cast(Generator[Session, None, None], provided)
            db = next(generator)
            return db, generator.close
        if isinstance(provided, Session):
            return provided, provided.close
    db = SessionLocal()
    return db, db.close


def _persist_usage(
    *,
    request: Request,
    api_key_id: UUID,
    tenant_id: UUID,
    method: str,
    path: str,
    status_code: int,
    request_id: str | None,
) -> None:
    db: Session | None = None
    close_session: Callable[[], Any] | None = None
    try:
        db, close_session = _open_usage_session(request)
        db.info["tenant_id"] = tenant_id
        api_key = db.scalar(
            select(APIKey).where(
                APIKey.id == api_key_id,
                APIKey.tenant_id == tenant_id,
            )
        )
        if api_key is None:
            return
        api_key.last_used_at = utc_now()
        db.add(
            APIKeyUsage(
                tenant_id=tenant_id,
                api_key_id=api_key_id,
                method=method[:10],
                path=path[:500],
                status_code=status_code,
                request_id=request_id[:100] if request_id else None,
            )
        )
        db.commit()
    except Exception:
        if db is not None:
            db.rollback()
        logger.exception("Failed to persist API-key usage for key %s", api_key_id)
    finally:
        if close_session is not None:
            close_session()


class APIKeyUsageMiddleware(BaseHTTPMiddleware):
    """Record every identified API-key request, including scope-denied calls."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def _record_usage(
        self,
        request: Request,
        *,
        status_code: int,
    ) -> None:
        api_key_id = getattr(request.state, "api_key_id", None)
        tenant_id = getattr(request.state, "api_key_tenant_id", None)
        if not isinstance(api_key_id, UUID) or not isinstance(tenant_id, UUID):
            return
        request_id = getattr(request.state, "request_id", None)
        await run_in_threadpool(
            _persist_usage,
            request=request,
            api_key_id=api_key_id,
            tenant_id=tenant_id,
            method=request.method,
            path=request.url.path,
            status_code=status_code,
            request_id=str(request_id) if request_id is not None else None,
        )

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        try:
            response = await call_next(request)
        except Exception:
            await self._record_usage(request, status_code=500)
            raise
        await self._record_usage(request, status_code=response.status_code)
        return response
