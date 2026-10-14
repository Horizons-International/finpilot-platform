"""Record authenticated API access outside endpoint transactions."""

import inspect
from collections.abc import Callable, Generator
from typing import Any, cast
from uuid import UUID

from fastapi import Request, Response
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from app.core.database import SessionLocal, get_db
from app.core.logger import get_logger
from app.services.security_event_service import record_security_event
from app.utils.date_time import utc_now

logger = get_logger(__name__)


def _open_session(request: Request) -> tuple[Session, Callable[[], Any]]:
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


def _persist_event(request: Request, response_status: int) -> None:
    user_id = getattr(request.state, "current_user_id", None)
    tenant_id = getattr(request.state, "tenant_id", None)
    api_key_id = getattr(request.state, "api_key_id", None)
    api_key_tenant_id = getattr(request.state, "api_key_tenant_id", None)

    if isinstance(user_id, str):
        try:
            user_id = UUID(user_id)
        except ValueError:
            user_id = None
    if isinstance(tenant_id, str):
        try:
            tenant_id = UUID(tenant_id)
        except ValueError:
            tenant_id = None
    if isinstance(api_key_id, str):
        try:
            api_key_id = UUID(api_key_id)
        except ValueError:
            api_key_id = None
    if isinstance(api_key_tenant_id, str):
        try:
            api_key_tenant_id = UUID(api_key_tenant_id)
        except ValueError:
            api_key_tenant_id = None

    if isinstance(user_id, UUID) and isinstance(tenant_id, UUID):
        event_type = "API_ACCESS"
        tenant_id_to_use = tenant_id
        details: dict[str, Any] = {
            "method": request.method,
            "response_status": response_status,
            "request_id": str(getattr(request.state, "request_id", ""))[:100],
        }
        user_id_to_use: UUID | None = user_id
        email = getattr(request.state, "current_user_email", None)
    elif isinstance(api_key_id, UUID) and isinstance(api_key_tenant_id, UUID):
        event_type = "API_KEY_ACCESS"
        tenant_id_to_use = api_key_tenant_id
        details = {
            "method": request.method,
            "response_status": response_status,
            "api_key_id": str(api_key_id),
            "request_id": str(getattr(request.state, "request_id", ""))[:100],
        }
        user_id_to_use = None
        email = None
    else:
        return

    db: Session | None = None
    close_session: Callable[[], Any] | None = None
    try:
        db, close_session = _open_session(request)
        db.info["tenant_id"] = tenant_id_to_use
        record_security_event(
            db,
            event_type=event_type,
            user_id=user_id_to_use,
            tenant_id=tenant_id_to_use,
            email=email,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            request_path=request.url.path,
            details=details,
        )
        session_id = getattr(request.state, "session_id", None)
        if isinstance(session_id, str):
            try:
                session_uuid = UUID(session_id)
                from app.models.user_session import UserSession

                active_session = db.get(UserSession, session_uuid)
                if (
                    active_session is not None
                    and active_session.tenant_id == tenant_id_to_use
                    and active_session.revoked_at is None
                ):
                    active_session.last_seen_at = utc_now()
            except ValueError:
                pass
        db.commit()
    except Exception:
        if db is not None:
            db.rollback()
        logger.exception("Could not persist security API-access event")
    finally:
        if close_session is not None:
            close_session()


class SecurityMonitoringMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        try:
            response = await call_next(request)
        except Exception:
            await run_in_threadpool(_persist_event, request, 500)
            raise
        await run_in_threadpool(_persist_event, request, response.status_code)
        return response
