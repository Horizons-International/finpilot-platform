from collections.abc import AsyncGenerator
from typing import cast
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.database import get_async_db, get_db
from app.main import app
from tests.conftest import TestSessionLocal


def test_health_check(client):
    response = client.get("/health")

    assert response.status_code == 200

    data = response.json()

    assert data["success"] is True
    assert data["message"] == "Application is healthy."
    assert data["data"]["status"] == "healthy"
    assert data["data"]["version"]
    assert data["data"]["environment"]


def test_readiness_check(client):
    response = client.get("/ready")

    assert response.status_code == 200

    data = response.json()

    assert data["success"] is True
    assert data["message"] == "Application is ready."
    assert data["data"]["status"] == "ready"
    assert data["data"]["database"] == "connected"
    assert data["data"]["version"]
    assert data["data"]["environment"]


def test_database_is_available():
    db = TestSessionLocal()

    try:
        result = db.execute(text("SELECT 1"))
        assert result.scalar() == 1
    finally:
        db.close()


def test_request_id_header(client):
    response = client.get("/health")

    assert response.status_code == 200

    request_id = response.headers.get("X-Request-ID")

    assert request_id is not None

    UUID(request_id)


def test_request_ids_are_unique(client):
    response1 = client.get("/health")
    response2 = client.get("/health")

    request_id1 = response1.headers["X-Request-ID"]
    request_id2 = response2.headers["X-Request-ID"]

    assert request_id1 != request_id2


def test_readiness_check_sync_database_unavailable(client):
    bad_engine = create_engine(
        "postgresql+psycopg://user:123789@localhost:5432/database_that_does_not_exist"
    )

    BadSessionLocal = sessionmaker(
        bind=bad_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    def override_get_db():
        db = BadSessionLocal()

        try:
            yield db
        finally:
            db.close()

    original_override = app.dependency_overrides[get_db]
    app.dependency_overrides[get_db] = override_get_db

    try:
        response = client.get("/ready")

        assert response.status_code == 503

        data = response.json()

        assert data["success"] is False
        assert data["message"] == "Application is not ready."
        assert data["data"]["status"] == "not_ready"
        assert data["data"]["database"] == "unavailable"

    finally:
        app.dependency_overrides[get_db] = original_override
        bad_engine.dispose()


def test_readiness_check_async_database_unavailable(client):
    class FailingAsyncSession:
        async def execute(self, statement: object) -> None:
            raise OperationalError(
                "SELECT 1", {}, RuntimeError("simulated async database failure")
            )

    async def override_get_async_db() -> AsyncGenerator[AsyncSession, None]:
        yield cast(AsyncSession, FailingAsyncSession())

    original_override = app.dependency_overrides[get_async_db]
    app.dependency_overrides[get_async_db] = override_get_async_db

    try:
        response = client.get("/ready")

        assert response.status_code == 503
        assert response.json()["data"]["database"] == "unavailable"
    finally:
        app.dependency_overrides[get_async_db] = original_override
