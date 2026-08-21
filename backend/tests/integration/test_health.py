from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.database import get_db
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


def test_readiness_check_database_unavailable(client):
    bad_engine = create_engine(
        "postgresql+psycopg://user:123789@localhost:5432/database_that_does_not_exist"
    )

    BadSessionLocal = sessionmaker(
        bind=bad_engine,
        autoflush=False,
        autocommit=False,
    )

    def override_get_db():
        db = BadSessionLocal()

        try:
            yield db
        finally:
            db.close()

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
        app.dependency_overrides.clear()
        bad_engine.dispose()
