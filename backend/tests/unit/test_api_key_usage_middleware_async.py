from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

import pytest
from starlette.requests import Request

from app.middleware import api_key_usage


class FakeKey:
    last_used_at = None


class FakeSession:
    def __init__(self, key: FakeKey) -> None:
        self.key = key
        self.info: dict[str, Any] = {}
        self.added: list[Any] = []
        self.committed = False

    async def scalar(self, statement: Any) -> FakeKey:
        return self.key

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def commit(self) -> None:
        self.committed = True


def _request() -> Request:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/v1/customers",
        "raw_path": b"/api/v1/customers",
        "query_string": b"",
        "headers": [],
        "client": ("testclient", 123),
        "server": ("testserver", 80),
        "state": {},
    }
    return Request(scope)


@pytest.mark.anyio
async def test_api_key_usage_is_persisted_with_async_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = FakeKey()
    session = FakeSession(key)

    @asynccontextmanager
    async def fake_session_context(request: Request):
        yield session

    monkeypatch.setattr(api_key_usage, "middleware_async_session", fake_session_context)
    request = _request()
    key_id = uuid4()
    tenant_id = uuid4()

    await api_key_usage._persist_usage(
        request=request,
        api_key_id=key_id,
        tenant_id=tenant_id,
        method="GET",
        path="/api/v1/customers",
        status_code=200,
        request_id="request-123",
    )

    assert session.info["tenant_id"] == tenant_id
    assert key.last_used_at is not None
    assert len(session.added) == 1
    usage = session.added[0]
    assert usage.api_key_id == key_id
    assert usage.tenant_id == tenant_id
    assert usage.method == "GET"
    assert usage.status_code == 200
    assert usage.request_id == "request-123"
    assert session.committed is True
