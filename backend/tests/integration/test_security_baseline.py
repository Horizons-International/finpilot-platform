"""PostgreSQL-backed checks for the idle-session security boundary."""

from datetime import timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import settings
from app.models.security_event import SecurityEvent
from app.models.user_session import UserSession
from app.utils.date_time import utc_now
from tests.conftest import TestSessionLocal


def test_idle_session_is_revoked_and_logged(
    client: TestClient,
    create_test_user,
) -> None:
    user = create_test_user(
        role="Auditor",
        email=f"idle-session-{uuid4()}@example.com",
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "Password123!"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["data"]["access_token"]

    # The opaque signed token contains the session UUID; find the session by user
    # rather than manually decoding JWT in the integration test.
    db = TestSessionLocal()
    try:
        user_session = (
            db.query(UserSession)
            .filter(UserSession.user_id == user.id)
            .order_by(UserSession.created_at.desc())
            .first()
        )
        assert user_session is not None
        session_id = user_session.id
        user_session.last_seen_at = utc_now() - timedelta(
            minutes=settings.SESSION_IDLE_TIMEOUT_MINUTES + 1
        )
        db.commit()
    finally:
        db.close()

    response = client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401, response.text

    db = TestSessionLocal()
    try:
        expired_session = (
            db.query(UserSession).filter(UserSession.id == session_id).first()
        )
        assert expired_session is not None
        assert expired_session.revoked_at is not None
        assert expired_session.revoked_reason == "idle_timeout"
        assert (
            db.query(SecurityEvent)
            .filter(
                SecurityEvent.user_id == user.id,
                SecurityEvent.event_type == "SESSION_IDLE_TIMEOUT",
            )
            .count()
            == 1
        )
    finally:
        db.close()


def test_unauthenticated_request_is_logged(client: TestClient) -> None:
    response = client.get("/api/v1/me")
    assert response.status_code == 401

    db = TestSessionLocal()
    try:
        events = (
            db.query(SecurityEvent)
            .filter(
                SecurityEvent.event_type == "AUTHENTICATION_REJECTED",
                SecurityEvent.request_path == "/api/v1/me",
            )
            .order_by(SecurityEvent.timestamp.desc())
            .all()
        )
        request_id = response.headers.get("x-request-id")
        event = next(
            (item for item in events if item.details.get("request_id") == request_id),
            None,
        )
        assert event is not None
        assert event.tenant_id is None
        assert event.details["response_status"] == 401
    finally:
        db.close()


def test_idle_session_refresh_is_denied_and_logged(
    client: TestClient,
    create_test_user,
) -> None:
    user = create_test_user(
        role="Auditor",
        email=f"idle-refresh-{uuid4()}@example.com",
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "Password123!"},
    )
    assert login.status_code == 200, login.text
    refresh_token = login.json()["data"]["refresh_token"]

    db = TestSessionLocal()
    try:
        user_session = (
            db.query(UserSession)
            .filter(UserSession.user_id == user.id)
            .order_by(UserSession.created_at.desc())
            .first()
        )
        assert user_session is not None
        session_id = user_session.id
        user_session.last_seen_at = utc_now() - timedelta(
            minutes=settings.SESSION_IDLE_TIMEOUT_MINUTES + 1
        )
        db.commit()
    finally:
        db.close()

    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 401, response.text

    db = TestSessionLocal()
    try:
        expired_session = (
            db.query(UserSession).filter(UserSession.id == session_id).first()
        )
        assert expired_session is not None
        assert expired_session.revoked_at is not None
        assert expired_session.revoked_reason == "idle_timeout"
        event = (
            db.query(SecurityEvent)
            .filter(
                SecurityEvent.user_id == user.id,
                SecurityEvent.event_type == "SESSION_IDLE_TIMEOUT",
            )
            .order_by(SecurityEvent.timestamp.desc())
            .first()
        )
        assert event is not None
        assert event.details["flow"] == "refresh"
    finally:
        db.close()
