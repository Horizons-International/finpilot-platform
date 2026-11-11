"""Async request guardrails, response security headers, and security auditing.

The rate limiter is intentionally bounded and process-local. Multi-process and
multi-replica deployments must also enforce shared quotas at the API gateway or
through a shared rate-limit store.
"""

from __future__ import annotations

import inspect
import math
import time
from collections import OrderedDict
from threading import RLock
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings
from app.middleware.async_session import middleware_async_session
from app.models.security_event import SecurityEvent
from app.models.user_session import UserSession
from app.utils.date_time import utc_now

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


def _uuid_or_none(value: Any) -> UUID | None:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        try:
            return UUID(value)
        except ValueError:
            return None
    return None


async def _persist_event(request: StarletteRequest, response_status: int) -> None:
    """Write a security event and update last-seen session with AsyncSession."""
    user_id = _uuid_or_none(getattr(request.state, "current_user_id", None))
    tenant_id = _uuid_or_none(getattr(request.state, "tenant_id", None))
    api_key_id = _uuid_or_none(getattr(request.state, "api_key_id", None))
    api_key_tenant_id = _uuid_or_none(getattr(request.state, "api_key_tenant_id", None))

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
        if user_id is not None and tenant_id is not None:
            event_tenant_id = tenant_id
            event_user_id = user_id
            email = getattr(request.state, "current_user_email", None)
        elif api_key_id is not None and api_key_tenant_id is not None:
            event_tenant_id = api_key_tenant_id
            event_user_id = None
            email = None
        else:
            event_tenant_id = None
            event_user_id = None
            email = None
    elif user_id is not None and tenant_id is not None:
        event_type = "API_ACCESS"
        event_tenant_id = tenant_id
        event_user_id = user_id
        email = getattr(request.state, "current_user_email", None)
    elif api_key_id is not None and api_key_tenant_id is not None:
        event_type = "API_KEY_ACCESS"
        event_tenant_id = api_key_tenant_id
        event_user_id = None
        email = None
    else:
        # Do not log every successful anonymous endpoint call.
        return

    details: dict[str, Any] = {
        "method": request.method,
        "response_status": response_status,
        "request_id": str(getattr(request.state, "request_id", ""))[:100],
    }
    if api_key_id is not None:
        details["api_key_id"] = str(api_key_id)

    try:
        async with middleware_async_session(request) as db:
            # Bind tenant context for tenant-owned writes. Clear it for anonymous
            # platform-level events so a reused test session cannot leak prior
            # request context into a global security event.
            if event_tenant_id is None:
                db.info.pop("tenant_id", None)
            else:
                db.info["tenant_id"] = event_tenant_id
            db.add(
                SecurityEvent(
                    tenant_id=event_tenant_id,
                    user_id=event_user_id,
                    email=email[:255] if isinstance(email, str) else None,
                    event_type=event_type[:64],
                    ip_address=request.client.host if request.client else None,
                    user_agent=request.headers.get("user-agent"),
                    request_path=request.url.path[:500],
                    details=details,
                )
            )

            session_id = getattr(request.state, "session_id", None)
            if response_status < 400 and isinstance(session_id, str):
                session_uuid = _uuid_or_none(session_id)
                if session_uuid is not None:
                    active_session = await db.scalar(
                        select(UserSession).where(UserSession.id == session_uuid)
                    )
                    if (
                        active_session is not None
                        and active_session.tenant_id == event_tenant_id
                        and active_session.revoked_at is None
                    ):
                        active_session.last_seen_at = utc_now()
            await db.commit()
    except Exception:
        # Security logging is best-effort and must not hide the API response.
        import logging

        logging.getLogger(__name__).exception("Could not persist security event")


class SecurityMonitoringMiddleware:
    """Pure ASGI middleware for request limits, headers, and security events."""

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
        current_time = time.monotonic() if now is None else now
        with self._bucket_lock:
            bucket = self._buckets.get(key)
            if bucket is None or current_time - bucket[0] >= window_seconds:
                self._buckets[key] = (current_time, 1)
                self._buckets.move_to_end(key)
                allowed, retry_after = True, 0
            elif bucket[1] >= limit:
                self._buckets.move_to_end(key)
                allowed = False
                retry_after = max(
                    1, math.ceil(window_seconds - (current_time - bucket[0]))
                )
            else:
                self._buckets[key] = (bucket[0], bucket[1] + 1)
                self._buckets.move_to_end(key)
                allowed, retry_after = True, 0

            while len(self._buckets) > settings.RATE_LIMIT_MAX_TRACKED_KEYS:
                self._buckets.popitem(last=False)
            return allowed, retry_after

    def _should_log_rate_limit(self, ip_address: str, path: str) -> bool:
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
            if _uuid_or_none(segment) is not None or segment.isdigit():
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
        if path == "/developer-portal" or path.startswith("/developer-portal/"):
            headers.append(
                (
                    b"content-security-policy",
                    (
                        b"default-src 'self'; script-src 'self'; style-src 'self'; "
                        b"img-src 'self' data:; connect-src 'self' http: https:; "
                        b"font-src 'self' data:; frame-ancestors 'none'; "
                        b"base-uri 'self'; form-action 'self'"
                    ),
                )
            )
        elif path not in {"/docs", "/redoc", "/openapi.json"}:
            headers.append(
                (
                    b"content-security-policy",
                    (
                        b"default-src 'none'; frame-ancestors 'none'; "
                        b"base-uri 'none'; form-action 'none'"
                    ),
                )
            )
        if (
            settings.ENVIRONMENT in {"staging", "production"}
            and settings.HSTS_MAX_AGE_SECONDS
        ):
            headers.append(
                (
                    b"strict-transport-security",
                    f"max-age={settings.HSTS_MAX_AGE_SECONDS}".encode("ascii"),
                )
            )
        return headers

    async def _persist(self, request: StarletteRequest, response_status: int) -> None:
        """Call async persistence, while tolerating simple sync test stubs."""
        result = _persist_event(request, response_status)
        if inspect.isawaitable(result):
            await result

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        state = scope.setdefault("state", {})
        state.setdefault("request_id", str(uuid4()))
        request = StarletteRequest(scope, receive=receive)
        path = str(scope.get("path", "/"))
        ip_address = self._client_ip(scope)
        response_status = 500

        async def secured_send(message: Message) -> None:
            nonlocal response_status
            if message["type"] == "http.response.start":
                response_status = int(message["status"])
                message = dict(message)
                current_headers = list(message.get("headers", []))
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
                await self._persist(request, code)

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
            await self._persist(request, 500)
            raise
        await self._persist(request, response_status)
