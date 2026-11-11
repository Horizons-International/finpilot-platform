from __future__ import annotations

import threading
from typing import Any
from uuid import UUID, uuid4

import pytest
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import Receive, Scope, Send

from app.middleware import audit_access
from app.middleware.audit_access import AuditAccessMiddleware


class FakeSession:
    def __init__(self) -> None:
        self.info: dict[str, Any] = {}
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


async def _empty_app(scope: Scope, receive: Receive, send: Send) -> None:
    return None


def _make_request(
    *,
    method: str = "GET",
    path: str = "/api/v1/customers/00000000-0000-0000-0000-000000000001",
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
) -> Request:
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "client": ("testclient", 123),
        "server": ("testserver", 80),
        "root_path": "",
        "route": type("Route", (), {"path": "/api/v1/customers/{customer_id}"})(),
    }
    request = Request(scope)
    if user_id is not None:
        request.state.current_user_id = str(user_id)
    if tenant_id is not None:
        request.state.tenant_id = str(tenant_id)
    request.state.request_id = "audit-access-test-request"
    return request


@pytest.mark.anyio
async def test_protected_read_persists_audit_in_worker_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    main_thread_id = threading.get_ident()
    captured: dict[str, Any] = {}
    user_id = uuid4()
    tenant_id = uuid4()
    customer_id = UUID("00000000-0000-0000-0000-000000000001")

    class FakeAuditEventService:
        def __init__(self, db: FakeSession, supplied_tenant_id: UUID) -> None:
            captured["service_thread_id"] = threading.get_ident()
            captured["db"] = db
            captured["tenant_id"] = supplied_tenant_id

        def record_data_access(self, **kwargs: Any) -> None:
            captured["event"] = kwargs

    monkeypatch.setattr(audit_access, "SessionLocal", lambda: session)
    monkeypatch.setattr(audit_access, "AuditEventService", FakeAuditEventService)

    middleware = AuditAccessMiddleware(_empty_app)
    request = _make_request(user_id=user_id, tenant_id=tenant_id)
    expected_response = Response(status_code=200)

    async def call_next(_: Request) -> Response:
        return expected_response

    response = await middleware.dispatch(
        request,
        call_next,
    )

    assert response is expected_response
    assert captured["service_thread_id"] != main_thread_id
    assert captured["tenant_id"] == tenant_id
    assert captured["db"] is session
    assert session.info == {
        "tenant_id": tenant_id,
        "tenant_user_id": user_id,
    }
    assert captured["event"] == {
        "user_id": user_id,
        "entity_type": "customers",
        "entity_id": customer_id,
        "access_type": "READ",
        "metadata": {
            "method": "GET",
            "route": "/api/v1/customers/{customer_id}",
            "status_code": 200,
            "request_id": "audit-access-test-request",
        },
    }
    assert session.committed is True
    assert session.rolled_back is False
    assert session.closed is True


@pytest.mark.anyio
async def test_audit_database_failure_does_not_change_business_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_to_create_session() -> FakeSession:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(audit_access, "SessionLocal", fail_to_create_session)
    middleware = AuditAccessMiddleware(_empty_app)
    request = _make_request(user_id=uuid4(), tenant_id=uuid4())
    expected_response = Response(status_code=200)

    async def call_next(_: Request) -> Response:
        return expected_response

    response = await middleware.dispatch(
        request,
        call_next,
    )

    assert response is expected_response
    assert response.status_code == 200


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method", "path", "status_code", "authenticated"),
    [
        ("POST", "/api/v1/customers", 201, True),
        ("GET", "/api/v1/health", 200, True),
        ("GET", "/api/v1/customers", 401, True),
        ("GET", "/api/v1/customers", 200, False),
    ],
)
async def test_non_qualifying_requests_are_not_audited(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    status_code: int,
    authenticated: bool,
) -> None:
    def unexpected_session() -> FakeSession:
        raise AssertionError("Audit session should not be created for this request")

    monkeypatch.setattr(audit_access, "SessionLocal", unexpected_session)
    middleware = AuditAccessMiddleware(_empty_app)
    request = _make_request(
        method=method,
        path=path,
        user_id=uuid4() if authenticated else None,
        tenant_id=uuid4() if authenticated else None,
    )
    expected_response = Response(status_code=status_code)

    async def call_next(_: Request) -> Response:
        return expected_response

    response = await middleware.dispatch(
        request,
        call_next,
    )

    assert response is expected_response
