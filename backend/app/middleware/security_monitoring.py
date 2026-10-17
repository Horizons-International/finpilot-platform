"""Request guardrails, security headers, and security-event persistence.

The request limiter is deliberately bounded and process-local: it protects a
single API process without adding a runtime dependency. Production deployments
with multiple workers/replicas must also apply shared rate limiting at the API
gateway or use a shared store.
"""

import inspect
import math
import time
from collections import OrderedDict
from collections.abc import Callable, Generator
from threading import RLock
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings
from app.core.database import SessionLocal, get_db
from app.core.logger import get_logger
from app.services.security_event_service import record_security_event
from app.utils.date_time import utc_now

logger = get_logger(__name__)

_SECURITY_HEADER_NAMES = {
    b"x-content-type-options",
    b"x-frame-options",
    b"referrer-policy",
    b"permissions-policy",
    b"cross-origin-opener-policy",
    b"cross-origin-resource-policy",
    b"x-permitted-cross-domain-policies",
    b"content-security-policy",
    b"strict-transport-security",
    b"cache-control",
    b"pragma",
}


def _open_session(request: Request) -> tuple[Session, Callable[[], Any]]:
    """Use the application's DB override in tests, or a fresh session in prod."""
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
    """Record authenticated traffic and denied/limited requests without secrets."""
    user_id = getattr(request.state, "current_user_id", None)
    tenant_id = getattr(request.state, "tenant_id", None)
    api_key_id = getattr(request.state, "api_key_id", None)
    api_key_tenant_id = getattr(request.state, "api_key_tenant_id", None)

    for variable, value in (
        ("user_id", user_id),
        ("tenant_id", tenant_id),
        ("api_key_id", api_key_id),
        ("api_key_tenant_id", api_key_tenant_id),
    ):
        if isinstance(value, str):
            try:
                parsed = UUID(value)
            except ValueError:
                parsed = None
            if variable == "user_id":
                user_id = parsed
            elif variable == "tenant_id":
                tenant_id = parsed
            elif variable == "api_key_id":
                api_key_id = parsed
            else:
                api_key_tenant_id = parsed

    security_event_types = {
        400: "REQUEST_REJECTED",
        401: "AUTHENTICATION_REJECTED",
        403: "AUTHORIZATION_DENIED",
        413: "REQUEST_TOO_LARGE",
        422: "INPUT_VALIDATION_REJECTED",
        429: "RATE_LIMIT_EXCEEDED",
    }

    if response_status in security_event_types:
        event_type = security_event_types[response_status]
        if isinstance(user_id, UUID) and isinstance(tenant_id, UUID):
            event_tenant_id: UUID | None = tenant_id
            event_user_id: UUID | None = user_id
            email = getattr(request.state, "current_user_email", None)
        elif isinstance(api_key_id, UUID) and isinstance(api_key_tenant_id, UUID):
            event_tenant_id = api_key_tenant_id
            event_user_id = None
            email = None
        else:
            event_tenant_id = None
            event_user_id = None
            email = None
    elif isinstance(user_id, UUID) and isinstance(tenant_id, UUID):
        event_type = "API_ACCESS"
        event_tenant_id = tenant_id
        event_user_id = user_id
        email = getattr(request.state, "current_user_email", None)
    elif isinstance(api_key_id, UUID) and isinstance(api_key_tenant_id, UUID):
        event_type = "API_KEY_ACCESS"
        event_tenant_id = api_key_tenant_id
        event_user_id = None
        email = None
    else:
        # Avoid logging every successful anonymous endpoint call.
        return

    details: dict[str, Any] = {
        "method": request.method,
        "response_status": response_status,
        "request_id": str(getattr(request.state, "request_id", ""))[:100],
    }
    if isinstance(api_key_id, UUID):
        details["api_key_id"] = str(api_key_id)

    db: Session | None = None
    close_session: Callable[[], Any] | None = None
    try:
        db, close_session = _open_session(request)
        # Anonymous rejected requests are intentionally stored as platform-wide
        # events with tenant_id=NULL; never infer identity from forwarded headers.
        db.info["tenant_id"] = event_tenant_id
        record_security_event(
            db,
            event_type=event_type,
            user_id=event_user_id,
            tenant_id=event_tenant_id,
            email=email,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            request_path=request.url.path,
            details=details,
        )

        session_id = getattr(request.state, "session_id", None)
        if response_status < 400 and isinstance(session_id, str):
            try:
                session_uuid = UUID(session_id)
                from app.models.user_session import UserSession

                active_session = db.get(UserSession, session_uuid)
                if (
                    active_session is not None
                    and active_session.tenant_id == event_tenant_id
                    and active_session.revoked_at is None
                ):
                    active_session.last_seen_at = utc_now()
            except ValueError:
                pass
        db.commit()
    except Exception:
        if db is not None:
            db.rollback()
        logger.exception("Could not persist security event")
    finally:
        if close_session is not None:
            close_session()


class SecurityMonitoringMiddleware:
    """Pure ASGI middleware for response headers, request limits, and audit logs."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._buckets: OrderedDict[str, tuple[float, int]] = OrderedDict()
        self._rate_limit_event_log_at: OrderedDict[str, float] = OrderedDict()
        self._bucket_lock = RLock()

    def _consume_bucket(
        self,
        key: str,
        *,
        limit: int,
        window_seconds: int,
        now: float | None = None,
    ) -> tuple[bool, int]:
        """Consume a bounded fixed-window bucket; return allowed and retry seconds."""
        current_time = time.monotonic() if now is None else now
        with self._bucket_lock:
            bucket = self._buckets.get(key)
            if bucket is None or current_time - bucket[0] >= window_seconds:
                self._buckets[key] = (current_time, 1)
                self._buckets.move_to_end(key)
                allowed = True
                retry_after = 0
            elif bucket[1] >= limit:
                self._buckets.move_to_end(key)
                allowed = False
                retry_after = max(
                    1, math.ceil(window_seconds - (current_time - bucket[0]))
                )
            else:
                self._buckets[key] = (bucket[0], bucket[1] + 1)
                self._buckets.move_to_end(key)
                allowed = True
                retry_after = 0

            while len(self._buckets) > settings.RATE_LIMIT_MAX_TRACKED_KEYS:
                self._buckets.popitem(last=False)
            return allowed, retry_after

    def _should_log_rate_limit(self, ip_address: str, path: str) -> bool:
        """Persist one 429 event per client/route/window, not every blocked hit."""
        now = time.monotonic()
        key = f"{ip_address}:{self._normalized_path(path)}"
        with self._bucket_lock:
            last_logged = self._rate_limit_event_log_at.get(key)
            if (
                last_logged is not None
                and now - last_logged < settings.RATE_LIMIT_WINDOW_SECONDS
            ):
                return False
            self._rate_limit_event_log_at[key] = now
            self._rate_limit_event_log_at.move_to_end(key)
            while (
                len(self._rate_limit_event_log_at)
                > settings.RATE_LIMIT_MAX_TRACKED_KEYS
            ):
                self._rate_limit_event_log_at.popitem(last=False)
            return True

    @staticmethod
    def _client_ip(scope: Scope) -> str:
        client = scope.get("client")
        if isinstance(client, tuple) and client:
            return str(client[0])
        return "unknown"

    @staticmethod
    def _normalized_path(path: str) -> str:
        """Collapse UUID/numeric path segments so IDs cannot evade route limits."""
        normalized: list[str] = []
        for segment in path.split("/"):
            if not segment:
                normalized.append(segment)
                continue
            try:
                UUID(segment)
                normalized.append("{id}")
                continue
            except ValueError:
                pass
            if segment.isdigit():
                normalized.append("{id}")
            else:
                normalized.append(segment[:100])
        return "/".join(normalized)

    @staticmethod
    def _is_sensitive_path(path: str) -> bool:
        return path in {
            "/api/v1/auth/login",
            "/api/v1/auth/refresh",
            "/api/v1/auth/accept-invitation",
        } or path.startswith("/api/v1/security/mfa")

    def _rate_limit(self, ip_address: str, path: str) -> tuple[bool, int]:
        if not settings.RATE_LIMIT_ENABLED:
            return True, 0

        normalized_path = self._normalized_path(path)
        checks = [
            (
                f"ip:{ip_address}",
                settings.RATE_LIMIT_REQUESTS_PER_IP,
                settings.RATE_LIMIT_WINDOW_SECONDS,
            ),
            (
                f"route:{ip_address}:{normalized_path}",
                settings.RATE_LIMIT_REQUESTS_PER_ROUTE,
                settings.RATE_LIMIT_WINDOW_SECONDS,
            ),
        ]
        if self._is_sensitive_path(path):
            checks.append(
                (
                    f"sensitive:{ip_address}:{normalized_path}",
                    settings.RATE_LIMIT_AUTH_REQUESTS,
                    settings.RATE_LIMIT_WINDOW_SECONDS,
                )
            )

        # Consume every applicable bucket so one exhausted category cannot be
        # bypassed by switching between another category and the same route.
        denied_retry_after = 0
        allowed = True
        for key, limit, window in checks:
            bucket_allowed, retry_after = self._consume_bucket(
                key, limit=limit, window_seconds=window
            )
            if not bucket_allowed:
                allowed = False
                denied_retry_after = max(denied_retry_after, retry_after)
        return allowed, denied_retry_after

    def _response_headers(self, path: str) -> list[tuple[bytes, bytes]]:
        if not settings.SECURITY_HEADERS_ENABLED:
            return []
        headers = [
            (b"x-content-type-options", b"nosniff"),
            (b"x-frame-options", b"DENY"),
            (b"referrer-policy", b"no-referrer"),
            (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
            (b"cross-origin-opener-policy", b"same-origin"),
            (b"cross-origin-resource-policy", b"same-origin"),
            (b"x-permitted-cross-domain-policies", b"none"),
            (b"cache-control", b"no-store"),
            (b"pragma", b"no-cache"),
        ]
        # Swagger/ReDoc require scripts and styles; CSP here targets API responses.
        if path not in {"/docs", "/redoc", "/openapi.json"}:
            headers.append(
                (
                    b"content-security-policy",
                    (
                        b"default-src 'none'; frame-ancestors 'none'; "
                        b"base-uri 'none'; form-action 'none'"
                    ),
                )
            )
        if settings.ENVIRONMENT == "production" and settings.HSTS_MAX_AGE_SECONDS:
            headers.append(
                (
                    b"strict-transport-security",
                    f"max-age={settings.HSTS_MAX_AGE_SECONDS}".encode("ascii"),
                )
            )
        return headers

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        state = scope.setdefault("state", {})
        state.setdefault("request_id", str(uuid4()))
        request = Request(scope, receive=receive)
        path = str(scope.get("path", "/"))
        ip_address = self._client_ip(scope)
        response_status = 500

        async def secured_send(message: Message) -> None:
            nonlocal response_status
            if message["type"] == "http.response.start":
                response_status = int(message["status"])
                message = dict(message)
                current_headers = list(message.get("headers", []))
                # Replace security headers so app code cannot accidentally weaken them.
                kept_headers = [
                    (name, value)
                    for name, value in current_headers
                    if name.lower() not in _SECURITY_HEADER_NAMES
                    and name.lower() != b"x-request-id"
                ]
                request_id = str(getattr(request.state, "request_id", ""))
                if request_id:
                    kept_headers.append(
                        (b"x-request-id", request_id.encode("ascii", errors="ignore"))
                    )
                message["headers"] = kept_headers + self._response_headers(path)
            await send(message)

        async def send_early_response(
            code: int,
            message: str,
            *,
            retry_after: int | None = None,
        ) -> None:
            headers: dict[str, str] = (
                {"Connection": "close"} if code in {400, 413, 429} else {}
            )
            if retry_after is not None:
                headers["Retry-After"] = str(retry_after)
            response = JSONResponse(
                status_code=code,
                content={
                    "success": False,
                    "message": message,
                    "data": None,
                    "errors": None,
                },
                headers=headers,
            )
            await response(scope, receive, secured_send)
            if code != 429 or self._should_log_rate_limit(ip_address, path):
                await run_in_threadpool(_persist_event, request, code)

        if scope.get("method") != "OPTIONS":
            allowed, retry_after = self._rate_limit(ip_address, path)
            if not allowed:
                await send_early_response(
                    429,
                    "Rate limit exceeded. Please retry later.",
                    retry_after=retry_after,
                )
                return

        raw_content_length = request.headers.get("content-length")
        if raw_content_length is not None:
            try:
                content_length = int(raw_content_length)
            except ValueError:
                await send_early_response(400, "Invalid Content-Length header.")
                return
            if content_length < 0:
                await send_early_response(400, "Invalid Content-Length header.")
                return
            if content_length > settings.MAX_REQUEST_BODY_BYTES:
                await send_early_response(
                    413,
                    "Request body exceeds the configured size limit.",
                )
                return

        # Buffer only up to the configured limit; this also handles chunked bodies
        # that do not carry a Content-Length header.
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                break
            if message["type"] != "http.request":
                continue
            body.extend(message.get("body", b""))
            if len(body) > settings.MAX_REQUEST_BODY_BYTES:
                await send_early_response(
                    413,
                    "Request body exceeds the configured size limit.",
                )
                return
            if not message.get("more_body", False):
                break

        replayed = False

        async def replay_receive() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {
                    "type": "http.request",
                    "body": bytes(body),
                    "more_body": False,
                }
            return {"type": "http.disconnect"}

        try:
            await self.app(scope, replay_receive, secured_send)
        except Exception:
            await run_in_threadpool(_persist_event, request, 500)
            raise
        await run_in_threadpool(_persist_event, request, response_status)
