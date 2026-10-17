"""Fast, database-free checks for security-baseline helpers and middleware."""

import asyncio
from collections.abc import Iterable
from typing import Any

import bcrypt
import pytest
from jose import JWTError, jwt
from pydantic import ValidationError
from starlette.types import Message, Scope

from app.core import security as core_security
from app.core.config import Settings, settings
from app.middleware import security_monitoring
from app.middleware.security_monitoring import SecurityMonitoringMiddleware


async def _dummy_app(scope: Any, receive: Any, send: Any) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": b"{}",
            "more_body": False,
        }
    )


def _call_asgi(
    middleware: SecurityMonitoringMiddleware,
    *,
    method: str = "GET",
    path: str = "/test",
    headers: Iterable[tuple[bytes, bytes]] = (),
    chunks: Iterable[tuple[bytes, bool]] = ((b"", False),),
) -> list[Message]:
    messages = iter(
        {
            "type": "http.request",
            "body": body,
            "more_body": more_body,
        }
        for body, more_body in chunks
    )
    sent: list[Message] = []

    async def receive() -> Message:
        try:
            return next(messages)
        except StopIteration:
            return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        sent.append(message)

    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": list(headers),
        "client": ("192.0.2.10", 12345),
        "server": ("testserver", 80),
        "state": {},
    }

    asyncio.run(middleware(scope, receive, send))
    return sent


def test_password_hashing_supports_long_passwords_without_truncation() -> None:
    password = "Aa1!" + ("long-password-segment-" * 5)
    stored_hash = core_security.hash_password(password)

    assert core_security.verify_password(password, stored_hash) is True
    assert core_security.verify_password(password + "x", stored_hash) is False


def test_password_verification_remains_compatible_with_legacy_bcrypt() -> None:
    legacy_password = b"LegacyPassword123!"
    legacy_hash = bcrypt.hashpw(legacy_password, bcrypt.gensalt()).decode("utf-8")

    assert core_security.verify_password(legacy_password.decode(), legacy_hash) is True
    assert core_security.verify_password("WrongPassword123!", legacy_hash) is False


def test_password_policy_enforces_length_and_complexity() -> None:
    with pytest.raises(ValueError, match="at least"):
        core_security.validate_password("Short123!")

    with pytest.raises(ValueError, match="uppercase"):
        core_security.validate_password("alllowercase123!")

    core_security.validate_password("GoodPassword123!")


def test_fixed_window_rate_limit_blocks_and_resets() -> None:
    middleware = SecurityMonitoringMiddleware(_dummy_app)

    first = middleware._consume_bucket("client", limit=2, window_seconds=60, now=10.0)
    second = middleware._consume_bucket("client", limit=2, window_seconds=60, now=11.0)
    blocked = middleware._consume_bucket("client", limit=2, window_seconds=60, now=12.0)
    after_reset = middleware._consume_bucket(
        "client", limit=2, window_seconds=60, now=70.0
    )

    assert first == (True, 0)
    assert second == (True, 0)
    assert blocked == (False, 58)
    assert after_reset == (True, 0)


def test_security_headers_are_added_to_responses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr(security_monitoring, "_persist_event", lambda *_: None)
    sent = _call_asgi(SecurityMonitoringMiddleware(_dummy_app))

    response_headers = dict(sent[0]["headers"])
    assert response_headers[b"x-content-type-options"] == b"nosniff"
    assert response_headers[b"x-frame-options"] == b"DENY"
    assert response_headers[b"cache-control"] == b"no-store"
    assert b"content-security-policy" in response_headers
    assert response_headers[b"x-request-id"]


def test_oversized_chunked_request_is_rejected_before_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr(settings, "MAX_REQUEST_BODY_BYTES", 4)
    persisted_statuses: list[int] = []
    monkeypatch.setattr(
        security_monitoring,
        "_persist_event",
        lambda _request, code: persisted_statuses.append(code),
    )
    endpoint_called = False

    async def endpoint(scope: Any, receive: Any, send: Any) -> None:
        nonlocal endpoint_called
        endpoint_called = True
        await _dummy_app(scope, receive, send)

    sent = _call_asgi(
        SecurityMonitoringMiddleware(endpoint),
        method="POST",
        path="/api/v1/customers",
        chunks=((b"123", True), (b"456", False)),
    )

    assert sent[0]["status"] == 413
    assert endpoint_called is False
    assert 413 in persisted_statuses


def test_path_rate_limit_normalizes_resource_ids() -> None:
    middleware = SecurityMonitoringMiddleware(_dummy_app)
    first = middleware._normalized_path(
        "/api/v1/customers/3ee8c7c6-9f1c-4aa0-8c95-3920a3e8a7f2"
    )
    second = middleware._normalized_path(
        "/api/v1/customers/11111111-1111-1111-1111-111111111111"
    )

    assert first == second
    assert first == "/api/v1/customers/{id}"


def test_access_tokens_without_expiration_are_rejected() -> None:
    token = jwt.encode(
        {"sub": "test-user", "type": "access"},
        settings.SECRET_KEY,
        algorithm="HS256",
    )

    with pytest.raises(JWTError):
        core_security.decode_access_token(token)


def test_access_tokens_without_subject_are_rejected() -> None:
    token = jwt.encode(
        {"exp": 4_000_000_000, "type": "access"},
        settings.SECRET_KEY,
        algorithm="HS256",
    )

    with pytest.raises(JWTError, match="subject"):
        core_security.decode_access_token(token)


def test_production_settings_reject_placeholder_signing_secret() -> None:
    with pytest.raises(ValidationError, match="Production SECRET_KEY"):
        Settings(
            DATABASE_URL="postgresql+psycopg://unused:unused@localhost/unused",
            SECRET_KEY="change-this-secret-key",
            ADMIN_EMAIL="admin@example.com",
            ADMIN_PASSWORD="StrongBootstrap123!",
            ENVIRONMENT="production",
        )


def test_rate_limit_event_logging_is_suppressed_within_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_REQUESTS_PER_IP", 1)
    monkeypatch.setattr(settings, "RATE_LIMIT_REQUESTS_PER_ROUTE", 100)
    monkeypatch.setattr(settings, "RATE_LIMIT_AUTH_REQUESTS", 100)
    monkeypatch.setattr(settings, "RATE_LIMIT_WINDOW_SECONDS", 60)
    persisted_statuses: list[int] = []
    monkeypatch.setattr(
        security_monitoring,
        "_persist_event",
        lambda _request, code: persisted_statuses.append(code),
    )
    middleware = SecurityMonitoringMiddleware(_dummy_app)

    first = _call_asgi(middleware)
    second = _call_asgi(middleware)
    third = _call_asgi(middleware)

    assert first[0]["status"] == 200
    assert second[0]["status"] == 429
    assert third[0]["status"] == 429
    assert persisted_statuses.count(429) == 1
