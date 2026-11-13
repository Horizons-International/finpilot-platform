from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from starlette.types import Scope

from app.core import exceptions


class FakeAsyncSession:
    def __init__(self) -> None:
        self.info: dict[str, Any] = {}
        self.committed = False
        self.rolled_back = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


def make_request(
    *,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    customer_id: UUID | None = None,
) -> Request:
    path = "/api/v1/customers"
    path_params: dict[str, str] = {}
    if customer_id is not None:
        path = f"/api/v1/customers/{customer_id}"
        path_params["customer_id"] = str(customer_id)

    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [(b"user-agent", b"pytest-agent")],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "root_path": "",
        "path_params": path_params,
    }
    request = Request(scope)
    if user_id is not None:
        request.state.current_user_id = str(user_id)
        request.state.current_user_email = "reviewer@example.test"
    if tenant_id is not None:
        request.state.tenant_id = str(tenant_id)
    request.state.request_id = "exception-audit-test-request"
    return request


@pytest.mark.anyio
async def test_404_access_denied_audit_uses_async_session_and_preserves_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeAsyncSession()
    captured: dict[str, Any] = {}
    user_id, tenant_id, customer_id = uuid4(), uuid4(), uuid4()

    @asynccontextmanager
    async def fake_session_context(request: Request):
        captured["request"] = request
        yield session

    class FakeAsyncAuditService:
        def __init__(self, db: FakeAsyncSession) -> None:
            captured["db"] = db

        async def log_event(self, **kwargs: Any) -> None:
            captured["event"] = kwargs

    monkeypatch.setattr(exceptions, "middleware_async_session", fake_session_context)
    monkeypatch.setattr(exceptions, "AsyncAuditService", FakeAsyncAuditService)

    response = await exceptions.http_exception_handler(
        make_request(user_id=user_id, tenant_id=tenant_id, customer_id=customer_id),
        HTTPException(status_code=404, detail="Customer not found."),
    )

    assert response.status_code == 404
    assert session.committed is True
    assert session.rolled_back is False
    assert session.info == {
        "tenant_id": tenant_id,
        "request_id": "exception-audit-test-request",
    }
    assert captured["db"] is session
    assert captured["event"] == {
        "event_type": exceptions.AuditEventType.ACCESS_DENIED,
        "user_id": user_id,
        "email": "reviewer@example.test",
        "ip_address": "127.0.0.1",
        "user_agent": "pytest-agent",
        "resource_type": "customer",
        "resource_id": customer_id,
    }


@pytest.mark.anyio
async def test_404_audit_failure_does_not_replace_original_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeAsyncSession()

    @asynccontextmanager
    async def fake_session_context(request: Request):
        yield session

    class FailingAsyncAuditService:
        def __init__(self, db: FakeAsyncSession) -> None:
            pass

        async def log_event(self, **kwargs: Any) -> None:
            raise RuntimeError("audit database unavailable")

    monkeypatch.setattr(exceptions, "middleware_async_session", fake_session_context)
    monkeypatch.setattr(exceptions, "AsyncAuditService", FailingAsyncAuditService)

    response = await exceptions.http_exception_handler(
        make_request(user_id=uuid4(), tenant_id=uuid4()),
        HTTPException(status_code=404, detail="Resource not found."),
    )

    assert response.status_code == 404
    assert session.committed is False
    assert session.rolled_back is True


@pytest.mark.anyio
async def test_404_without_authenticated_user_does_not_open_audit_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @asynccontextmanager
    async def unexpected_session_context(request: Request):
        raise AssertionError("Unauthenticated 404s must not create an audit session")
        yield  # pragma: no cover

    monkeypatch.setattr(
        exceptions, "middleware_async_session", unexpected_session_context
    )

    response = await exceptions.http_exception_handler(
        make_request(), HTTPException(status_code=404, detail="Not found.")
    )
    assert response.status_code == 404


@pytest.mark.anyio
async def test_non_404_exception_does_not_create_access_denied_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @asynccontextmanager
    async def unexpected_session_context(request: Request):
        raise AssertionError("Only 404s should create access-denied audit events")
        yield  # pragma: no cover

    monkeypatch.setattr(
        exceptions, "middleware_async_session", unexpected_session_context
    )

    response = await exceptions.http_exception_handler(
        make_request(user_id=uuid4(), tenant_id=uuid4()),
        HTTPException(status_code=403, detail="Forbidden."),
    )
    assert response.status_code == 403
